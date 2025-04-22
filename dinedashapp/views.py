from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.timezone import now as datetime_now
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from dinedashapp.forms import (
    CreateOrderItemForm,
    DeliveryAccountDetailsForm,
    DeliveryContractorLogInForm,
    DeliveryContractorRegistrationForm,
    OrdersWithinDistanceForm,
    OrdersWithStatusForm,
    RegularAccountDetailsForm,
    RegularUserLogInForm,
    RegularUserRegistrationForm,
    RestaurantInfoForm,
    RestaurantLogInForm,
    RestaurantRegistrationForm,
)
from dinedashapp.geo import get_distance_in_miles
from dinedashapp.models import (
    BlogPost,
    MenuItem,
    Order,
    OrderItem,
    Payment,
    Restaurant,
    RestaurantReview,
    User,
)


def check_authorization(user, target):
    return (target is None and not user.is_authenticated) or (
        (user.is_authenticated) and (target == user.user_type)
    )


def deny_if_not_target(target):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if check_authorization(request.user, target):
                return func(request, *args, **kwargs)
            raise PermissionDenied()

        return wrapper

    return decorator


def index(request):
    pricing_examples = MenuItem.objects.all()[:4]
    return render(
        request,
        "dinedashapp/index.html",
        {"pricing_examples": pricing_examples},
    )


def about_us(request):
    return render(request, "dinedashapp/about_us.html")


def contact_us(request):
    return render(request, "dinedashapp/contact_us.html")


def blog(request):
    posts = BlogPost.objects.all()
    return render(request, "dinedashapp/blog.html", {"blog_posts": posts})


@deny_if_not_target(None)
def log_in_question(request):
    return render(request, "dinedashapp/log_in_question.html")


class AnonymousUserRequiredMixin:
    target = None

    def dispatch(self, *args, **kwargs):
        if check_authorization(self.request.user, self.target):
            return super().dispatch(*args, **kwargs)
        raise PermissionDenied()


class RegularUserRequiredMixin(AnonymousUserRequiredMixin):
    target = "Reg"


class RestaurantUserRequiredMixin(AnonymousUserRequiredMixin):
    target = "Res"


class DeliveryUserRequiredMixin(AnonymousUserRequiredMixin):
    target = "Del"


class AuthenticationRequiredMixin:
    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            return super().dispatch(*args, **kwargs)
        raise PermissionDenied()


class RegularLogInView(AnonymousUserRequiredMixin, FormView):
    template_name = "dinedashapp/log_in_form.html"
    form_class = RegularUserLogInForm
    extra_context = {
        "title": "Regular Customer Log In",
        "registration_url": reverse_lazy("register_regular"),
    }
    success_url = reverse_lazy("index")

    def form_valid(self, form):
        login(self.request, form.user)
        return redirect(self.get_success_url())


class RestaurantLogInView(RegularLogInView):
    form_class = RestaurantLogInForm
    extra_context = {
        "title": "Restaurant Log In",
        "registration_url": reverse_lazy("register_restaurant"),
    }

    def form_valid(self, form):
        login(self.request, form.user)
        return redirect("restaurant_info", pk=form.user.restaurant.pk)


class DeliveryLogInView(RegularLogInView):
    form_class = DeliveryContractorLogInForm
    extra_context = {
        "title": "Delivery Contractor Log In",
        "registration_url": reverse_lazy("register_delivery"),
    }
    success_url = reverse_lazy("delivery_orders")


class RegularRegistrationView(AnonymousUserRequiredMixin, FormView):
    template_name = "dinedashapp/registration_form.html"
    form_class = RegularUserRegistrationForm
    extra_context = {
        "title": "Regular Customer Registration",
        "log_in_url": reverse_lazy("log_in_regular"),
    }

    def form_valid(self, form):
        form.save()

        email = form.cleaned_data["email"]
        password = form.cleaned_data["password1"]

        user = authenticate(email=email, password=password)

        login(self.request, user)
        return redirect("index")


class RestaurantRegistrationView(RegularRegistrationView):
    form_class = RestaurantRegistrationForm
    extra_context = {
        "title": "Restaurant Registration",
        "log_in_url": reverse_lazy("log_in_restaurant"),
    }

    def form_valid(self, form):
        form.save()

        email = form.cleaned_data["email"]
        password = form.cleaned_data["password1"]

        user = authenticate(email=email, password=password)

        login(self.request, user)
        return redirect("restaurant_info", pk=user.restaurant.id)


class DeliveryRegistrationView(RegularRegistrationView):
    form_class = DeliveryContractorRegistrationForm
    extra_context = {
        "title": "Delivery Contractor Registration",
        "log_in_url": reverse_lazy("log_in_delivery"),
    }

    def form_valid(self, form):
        form.save()

        email = form.cleaned_data["email"]
        password = form.cleaned_data["password1"]

        user = authenticate(email=email, password=password)

        login(self.request, user)
        return redirect("delivery_orders")


def log_out(request):
    logout(request)
    return redirect("index")


class RestaurantSearchView(ListView):
    template_name = "dinedashapp/restaurant_search.html"
    context_object_name = "restaurants"

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        if query := self.request.GET.get("query"):
            kwargs["query"] = query
        if order_by := self.request.GET.get("order_by"):
            kwargs["order_by"] = order_by
        if (
            (user := self.request.user).is_authenticated
            and user.user_type == "Reg"
            and user.customer_info.location
        ):
            kwargs["user_has_location"] = True
        return kwargs

    def get_queryset(self):
        queryset = Restaurant.objects.values(
            "pk",
            "name",
            "description",
            "location_x_coordinate",
            "location_y_coordinate",
        ).annotate(average_rating=Avg("reviews__rating"))

        if query := self.request.GET.get("query"):
            query = query.strip().replace("  ", " ")
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )

        if (order_by := self.request.GET.get("order_by")) == "name":
            queryset = queryset.order_by("name")
        elif order_by == "-name":
            queryset = queryset.order_by("-name")
        elif order_by == "highest_rating":
            # Only includes restaurants that have reviews.
            queryset = queryset.filter(average_rating__gt=0).order_by(
                "-average_rating", "name"
            )
        elif order_by == "lowest_rating":
            # Only includes restaurants that have reviews.
            queryset = queryset.filter(average_rating__gt=0).order_by(
                "average_rating", "name"
            )
        else:
            queryset = queryset.order_by("name")

        user = self.request.user
        user_has_location = (
            user.is_authenticated
            and user.user_type == "Reg"
            and user.customer_info.location
        )

        if user_has_location:
            user_coordinates = (
                user.customer_info.location_x_coordinate,
                user.customer_info.location_y_coordinate,
            )
            result = map(
                lambda r: r
                | {
                    "distance_away": get_distance_in_miles(
                        (r["location_x_coordinate"], r["location_y_coordinate"]),
                        user_coordinates,
                    )
                },
                queryset,
            )
        else:
            result = queryset

        if order_by == "lowest_distance" and user_has_location:
            result = sorted(
                result,
                key=lambda r: r["distance_away"],
            )

        return result


class RestaurantInfoView(DetailView):
    model = Restaurant
    template_name = "dinedashapp/restaurant_info.html"
    context_object_name = "restaurant"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()

        user = self.request.user
        context["is_owner"] = (
            user.is_authenticated and user.user_type == "Res" and user.restaurant == obj
        )

        context["sunday_hours"] = (
            f"{obj.open_hour_sunday.strftime("%I:%M %p").lstrip("0")} to {obj.close_hour_sunday.strftime("%I:%M %p").lstrip("0")}"
            if obj.open_hour_sunday is not None
            else "closed"
        )
        context["monday_hours"] = (
            f"{obj.open_hour_monday.strftime("%I:%M %p").lstrip("0")} to {obj.close_hour_monday.strftime("%I:%M %p").lstrip("0")}"
            if obj.open_hour_monday is not None
            else "closed"
        )
        context["tuesday_hours"] = (
            f"{obj.open_hour_tuesday.strftime("%I:%M %p").lstrip("0")} to {obj.close_hour_tuesday.strftime("%I:%M %p").lstrip("0")}"
            if obj.open_hour_tuesday is not None
            else "closed"
        )
        context["wednesday_hours"] = (
            f"{obj.open_hour_wednesday.strftime("%I:%M %p").lstrip("0")} to {obj.close_hour_wednesday.strftime("%I:%M %p").lstrip("0")}"
            if obj.open_hour_wednesday is not None
            else "closed"
        )
        context["thursday_hours"] = (
            f"{obj.open_hour_thursday.strftime("%I:%M %p").lstrip("0")} to {obj.close_hour_thursday.strftime("%I:%M %p").lstrip("0")}"
            if obj.open_hour_thursday is not None
            else "closed"
        )
        context["friday_hours"] = (
            f"{obj.open_hour_friday.strftime("%I:%M %p").lstrip("0")} to {obj.close_hour_friday.strftime("%I:%M %p").lstrip("0")}"
            if obj.open_hour_friday is not None
            else "closed"
        )
        context["saturday_hours"] = (
            f"{obj.open_hour_saturday.strftime("%I:%M %p").lstrip("0")} to {obj.close_hour_saturday.strftime("%I:%M %p").lstrip("0")}"
            if obj.open_hour_saturday is not None
            else "closed"
        )

        context["average_rating"] = obj.get_average_rating()

        if user.is_authenticated and user.user_type == "Reg":
            context["is_favorite"] = (
                obj in user.customer_info.favorite_restaurants.all()
            )

            if (
                order := user.orders.annotate(order_item_count=Count("items"))
                .filter(status=Order.OrderStatus.NOT_PLACED_YET, order_item_count__gt=0)
                .first()
            ):
                context["url_for_order"] = reverse(
                    "manage_order", kwargs={"pk": order.id}
                )

        return context


class ModifyFavoriteStatus(RegularUserRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        restaurant_id = kwargs["pk"]
        obj = Restaurant.objects.get(id=restaurant_id)
        if kwargs["status"]:
            obj.favorited_by.add(self.request.user.customer_info)
        else:
            obj.favorited_by.remove(self.request.user.customer_info)
        return redirect("restaurant_info", restaurant_id)


class CreateMenuItemView(RestaurantUserRequiredMixin, CreateView):
    model = MenuItem
    fields = ("name", "price", "description")
    template_name = "dinedashapp/menu_item_form.html"

    def form_valid(self, form):
        obj = form.save(False)
        obj.restaurant = self.request.user.restaurant
        obj.save()
        return redirect("restaurant_info", obj.restaurant.pk)


class EditMenuItemView(RestaurantUserRequiredMixin, UpdateView):
    model = MenuItem
    fields = ("name", "price", "description")
    template_name = "dinedashapp/menu_item_form.html"

    def get_queryset(self):
        return super().get_queryset().filter(restaurant__user=self.request.user)

    def get_success_url(self):
        return reverse("restaurant_info", kwargs={"pk": self.object.restaurant.pk})


class EditRestaurantInfoView(RestaurantUserRequiredMixin, UpdateView):
    form_class = RestaurantInfoForm
    template_name = "dinedashapp/restaurant_info_form.html"

    def get_object(self, queryset=None):
        return self.request.user.restaurant

    def get_success_url(self):
        return reverse(
            "restaurant_info", kwargs={"pk": self.request.user.restaurant.id}
        )


class ListOfReviewsView(ListView):
    template_name = "dinedashapp/restaurant_reviews_list.html"
    context_object_name = "reviews"

    def get_queryset(self):
        return RestaurantReview.objects.filter(
            restaurant__pk=self.kwargs["restaurant_id"]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurant"] = Restaurant.objects.get(pk=self.kwargs["restaurant_id"])
        context["review_from_user_exists"] = (
            self.get_queryset().filter(user__pk=self.request.user.id).exists()
        )
        return context


class CreateReviewView(RegularUserRequiredMixin, CreateView):
    model = RestaurantReview
    fields = ("rating", "description")
    template_name = "dinedashapp/restaurant_review_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurant_id"] = self.kwargs["restaurant_id"]
        return context

    def form_valid(self, form):
        obj = form.save(False)
        restaurant_id = self.kwargs["restaurant_id"]
        obj.restaurant_id = restaurant_id
        obj.user = self.request.user
        obj.save()
        return redirect("restaurant_reviews", restaurant_id)


class EditReviewView(RegularUserRequiredMixin, UpdateView):
    model = RestaurantReview
    fields = ("rating", "description")
    template_name = "dinedashapp/restaurant_review_form.html"

    def get_object(self, queryset=None):
        return RestaurantReview.objects.get(
            user__pk=self.request.user.id, restaurant__pk=self.kwargs["restaurant_id"]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["restaurant_id"] = self.kwargs["restaurant_id"]
        context["can_delete"] = True
        return context

    def get_success_url(self):
        restaurant_id = self.object.restaurant.id
        return reverse("restaurant_reviews", kwargs={"restaurant_id": restaurant_id})


class DeleteReviewView(RegularUserRequiredMixin, DeleteView):
    template_name = "dinedashapp/restaurant_review_confirm_delete.html"

    def get_object(self, queryset=None):
        return RestaurantReview.objects.get(
            user__pk=self.request.user.id, pk=self.kwargs["review_id"]
        )

    def get_success_url(self):
        restaurant_id = self.object.restaurant.id
        return reverse("restaurant_reviews", kwargs={"restaurant_id": restaurant_id})


def get_url_after_change(user):
    match user.user_type:
        case "Reg":
            return reverse("regular_account")
        case "Res":
            return reverse("restaurant_info", kwargs={"pk": user.restaurant.pk})
        case "Del":
            return reverse("delivery_orders")


class ChangeEmailView(AuthenticationRequiredMixin, UpdateView):
    model = User
    fields = ("email",)
    template_name = "dinedashapp/change_email_form.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return get_url_after_change(self.request.user)


class ChangePasswordView(AuthenticationRequiredMixin, PasswordChangeView):
    template_name = "dinedashapp/change_password_form.html"

    def get_success_url(self):
        return get_url_after_change(self.request.user)


class RegularAccountView(RegularUserRequiredMixin, TemplateView):
    template_name = "dinedashapp/regular_account.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["favorite_restaurants"] = (
            self.request.user.customer_info.favorite_restaurants.all()
        )
        return context


class EditRegularAccountDetailsView(RegularUserRequiredMixin, UpdateView):
    form_class = RegularAccountDetailsForm
    template_name = "dinedashapp/edit_account_details.html"
    success_url = reverse_lazy("regular_account")

    def get_object(self, queryset=None):
        return self.request.user.customer_info


class EditDeliveryAccountDetailsView(DeliveryUserRequiredMixin, UpdateView):
    form_class = DeliveryAccountDetailsForm
    template_name = "dinedashapp/edit_account_details.html"
    success_url = reverse_lazy("delivery_orders")

    def get_object(self, queryset=None):
        return self.request.user.delivery_contractor_info


class CreateOrderItemView(RegularUserRequiredMixin, CreateView):
    model = OrderItem
    form_class = CreateOrderItemForm
    template_name = "dinedashapp/order_item_form.html"

    def get(self, request, *args, **kwargs):
        menu_item_id = kwargs["menu_item_id"]
        order_item = (
            OrderItem.objects.filter(
                order__user=request.user,
                menu_item_id=menu_item_id,
                order__status=Order.OrderStatus.NOT_PLACED_YET,
            )
            .order_by("order__id")
            .first()
        )
        if order_item:
            return redirect("edit_order_item", pk=order_item.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["menu_item"] = MenuItem.objects.get(pk=self.kwargs["menu_item_id"])
        return kwargs

    def form_valid(self, form):
        obj = form.save(False)
        menu_item = MenuItem.objects.get(pk=self.kwargs["menu_item_id"])
        order, _created = Order.objects.get_or_create(
            restaurant_id=menu_item.restaurant.id,
            user_id=self.request.user.id,
            status=Order.OrderStatus.NOT_PLACED_YET,
        )
        obj.order_id = order.id
        obj.menu_item_id = menu_item.id
        obj.save()
        return redirect("manage_order", order.id)


class EditOrderItemView(RegularUserRequiredMixin, UpdateView):
    model = OrderItem
    fields = ("quantity",)
    template_name = "dinedashapp/order_item_form.html"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                order__user=self.request.user,
                order__status=Order.OrderStatus.NOT_PLACED_YET,
            )
            .order_by("order__id")
        )

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["menu_item"] = self.object.menu_item
        kwargs["editing"] = True
        return kwargs

    def form_valid(self, form):
        if form.cleaned_data["quantity"] == 0:
            # pylint: disable=attribute-defined-outside-init
            self.object = self.get_object()
            self.object.delete()
            return redirect(self.get_success_url())
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("manage_order", kwargs={"pk": self.object.order.id})


class ManageOrder(RegularUserRequiredMixin, DetailView):
    model = Order
    template_name = "dinedashapp/manage_order.html"

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class PlaceOrderView(RegularUserRequiredMixin, CreateView):
    model = Payment
    fields = (
        "payment_method",
        "cardholder_name",
        "billing_address",
        "card_number",
        "expiration_month",
        "expiration_year",
        "cvv",
    )
    template_name = "dinedashapp/place_order_form.html"

    def dispatch(self, *args, **kwargs):
        user = self.request.user
        if user.user_type == "Reg" and user.customer_info.location:
            return super().dispatch(*args, **kwargs)
        raise PermissionDenied()

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data(**kwargs)
        kwargs["order"] = Order.objects.get(
            user=self.request.user,
            pk=self.kwargs["order_id"],
            status=Order.OrderStatus.NOT_PLACED_YET,
        )
        return kwargs

    def form_valid(self, form):
        obj = form.save(False)
        obj.order = order = Order.objects.get(
            user=self.request.user,
            pk=self.kwargs["order_id"],
            status=Order.OrderStatus.NOT_PLACED_YET,
        )
        obj.user = self.request.user
        obj.amount_paid = order.total_cost = order.calc_total_cost()
        obj.save()

        order.status = Order.OrderStatus.PLACED
        order.date_placed = datetime_now()
        order.save()

        return redirect("manage_order", pk=order.id)


@deny_if_not_target("Res")
@csrf_exempt
def restaurant_orders_list(request):
    restaurant = request.user.restaurant
    if (
        request.method == "POST"
        and request.POST.get("action") == "mark_as_ready_for_pickup"
    ):
        order_id = int(request.POST.get("order_id"))
        order = Order.objects.get(
            pk=order_id,
            restaurant=restaurant,
            status=Order.OrderStatus.PLACED,
        )
        order.status = Order.OrderStatus.READY_FOR_PICKUP
        order.save()

    return render(
        request,
        "dinedashapp/restaurant_orders_list.html",
        {
            "orders": Order.objects.filter(
                restaurant=restaurant, status=Order.OrderStatus.PLACED
            )
        },
    )


@deny_if_not_target("Del")
@csrf_exempt
def delivery_orders_list(request):
    user = request.user.delivery_contractor_info
    if request.method == "POST":
        order_id = int(request.POST.get("order_id"))
        status_queried = ""
        match request.POST.get("action"):
            case "accept":
                order = Order.objects.get(
                    pk=order_id,
                    status=Order.OrderStatus.READY_FOR_PICKUP,
                    accepted_by__isnull=True,
                )
                order.accepted_by = user
                order.status = Order.OrderStatus.IN_TRANSIT
                order.save()

            case "reject":
                order = Order.objects.exclude(accepted_by=user).get(pk=order_id)
                order.rejected_by.add(user)

            case "mark_as_delivered":
                order = Order.objects.get(
                    pk=order_id, status=Order.OrderStatus.IN_TRANSIT
                )
                order.status = Order.OrderStatus.DELIVERED
                order.date_delivered = datetime_now()
                order.save()

                status_queried = "accepted"

            case "set_minutes_away":
                order = Order.objects.get(
                    pk=order_id, status=Order.OrderStatus.IN_TRANSIT
                )
                try:
                    order.minutes_away = int(request.POST.get("minutes_away", ""))
                    print("success")
                except ValueError:
                    print("failed")
                    order.minutes_away = None
                order.save()

                status_queried = "accepted"

    else:
        status_queried = request.GET.get("status")

    if status_queried == "accepted":
        orders = user.accepted_orders.filter(status=Order.OrderStatus.IN_TRANSIT)
    else:
        orders = Order.objects.filter(
            status=Order.OrderStatus.READY_FOR_PICKUP
        ).exclude(id__in=user.rejected_orders.all())

    orders = orders.values(
        "id",
        "restaurant__location",
        "restaurant__location_x_coordinate",
        "restaurant__location_y_coordinate",
        "user__customer_info__location",
        "user__customer_info__location_x_coordinate",
        "user__customer_info__location_y_coordinate",
        "minutes_away",
    )

    delivery_user_coordinates = (
        user.location_x_coordinate,
        user.location_y_coordinate,
    )

    orders = map(
        lambda o: o
        | {
            "restaurant_distance_away": get_distance_in_miles(
                (
                    o["restaurant__location_x_coordinate"],
                    o["restaurant__location_y_coordinate"],
                ),
                delivery_user_coordinates,
            ),
            "user_distance_away": get_distance_in_miles(
                (
                    o["user__customer_info__location_x_coordinate"],
                    o["user__customer_info__location_y_coordinate"],
                ),
                delivery_user_coordinates,
            ),
        },
        orders,
    )

    if status_queried == "accepted":
        return render(
            request,
            "dinedashapp/delivery_orders_list.html",
            {"orders": orders, "status_queried": status_queried},
        )

    form = OrdersWithinDistanceForm(
        {
            "max_distance": (
                request.POST if request.method == "POST" else request.GET
            ).get("max_distance", 5)
        }
    )
    max_distance = form.cleaned_data["max_distance"] if form.is_valid() else 5
    orders = filter(
        lambda o: o["restaurant_distance_away"] <= max_distance
        and o["user_distance_away"] <= max_distance,
        orders,
    )

    return render(
        request,
        "dinedashapp/delivery_orders_list.html",
        {
            "orders": orders,
            "status_queried": status_queried,
            "form": form,
            "max_distance": (max_distance),
        },
    )


@deny_if_not_target("Reg")
def regular_customer_orders_list(request):
    orders = (
        Order.objects.filter(user=request.user)
        .exclude(status=Order.OrderStatus.NOT_PLACED_YET)
        .order_by("-date_placed", "-id")
    )
    status_queried = request.GET.get("status")
    the_filter = None
    if status_queried:
        form = OrdersWithStatusForm(data={"status": status_queried})
        if form.is_valid():
            the_filter = Order.OrderStatus(status_queried).label.lower()
            orders = orders.filter(status=form.cleaned_data["status"])
    else:
        form = OrdersWithStatusForm()
    return render(
        request,
        "dinedashapp/regular_customer_orders_list.html",
        {"orders": orders, "form": form, "filter": the_filter},
    )
