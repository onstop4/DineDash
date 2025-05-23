from datetime import datetime, timedelta

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import BaseUserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.timezone import now as datetime_now
from geopy.exc import GeopyError

from dinedashapp.geo import get_coordinates
from dinedashapp.models import (
    CustomerInfo,
    DeliveryContractorInfo,
    Order,
    OrderItem,
    Reservation,
    Restaurant,
    Table,
    User,
)


class AbstractLogInForm(forms.Form):
    user_type: str
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput())

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        super().clean()
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password"]
        self.user = authenticate(email=email, password=password)
        if not self.user:
            raise ValidationError("Email and password are incorrect.")
        if self.user.user_type != self.user_type:
            raise ValidationError(
                "This form is not intended for the type of account associated with the credentials you provided."
            )


class RegularUserLogInForm(AbstractLogInForm):
    user_type = "Reg"


class RestaurantLogInForm(AbstractLogInForm):
    user_type = "Res"


class DeliveryContractorLogInForm(AbstractLogInForm):
    user_type = "Del"


class AbstractUserCreationForm(BaseUserCreationForm):
    user_type: str

    class Meta:
        model = User
        fields = ("email",)

    def clean_email(self):
        """Reject emails that differ only in case."""
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email address already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = self.user_type
        if commit:
            user.save()
        return user


class RegularUserRegistrationForm(AbstractUserCreationForm):
    user_type = "Reg"
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    location = forms.CharField(label="Your location", max_length=300, required=False)

    def clean(self):
        if location := self.cleaned_data.get("location", "").strip():
            try:
                match get_coordinates(location):
                    case [x, y]:
                        self.cleaned_data["location_x_coordinate"] = x
                        self.cleaned_data["location_y_coordinate"] = y
                    case _:
                        raise ValidationError("Could not find location.")
            except GeopyError as e:
                raise ValidationError("Could not find location.") from e

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            CustomerInfo.objects.create(
                user=user,
                first_name=self.cleaned_data["first_name"],
                last_name=self.cleaned_data["last_name"],
                location=(location := self.cleaned_data.get("location")),
                location_x_coordinate=(
                    self.cleaned_data["location_x_coordinate"] if location else None
                ),
                location_y_coordinate=(
                    self.cleaned_data["location_y_coordinate"] if location else None
                ),
            )
        return user


class RestaurantRegistrationForm(AbstractUserCreationForm):
    user_type = "Res"
    restaurant_name = forms.CharField(max_length=200)
    description = forms.CharField(max_length=1000)
    location = forms.CharField(max_length=300)

    def clean(self):
        if location := self.cleaned_data.get("location", "").strip():
            try:
                match get_coordinates(location):
                    case [x, y]:
                        self.cleaned_data["location_x_coordinate"] = x
                        self.cleaned_data["location_y_coordinate"] = y
                    case _:
                        raise ValidationError("Could not find location.")
            except GeopyError as e:
                raise ValidationError("Could not find location.") from e
        else:
            raise ValidationError("You need to include a valid location.")

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            Restaurant.objects.create(
                user=user,
                name=self.cleaned_data["restaurant_name"],
                description=self.cleaned_data["description"],
                location=(location := self.cleaned_data["location"]),
                location_x_coordinate=(
                    self.cleaned_data["location_x_coordinate"] if location else None
                ),
                location_y_coordinate=(
                    self.cleaned_data["location_y_coordinate"] if location else None
                ),
            )
        return user


class DeliveryContractorRegistrationForm(AbstractUserCreationForm):
    user_type = "Del"
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    location = forms.CharField(max_length=300)

    def clean(self):
        if location := self.cleaned_data.get("location", "").strip():
            try:
                match get_coordinates(location):
                    case [x, y]:
                        self.cleaned_data["location_x_coordinate"] = x
                        self.cleaned_data["location_y_coordinate"] = y
                    case _:
                        raise ValidationError("Could not find location.")
            except GeopyError as e:
                raise ValidationError("Could not find location.") from e
        else:
            raise ValidationError("You need to include a valid location.")

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            DeliveryContractorInfo.objects.create(
                user=user,
                first_name=self.cleaned_data["first_name"],
                last_name=self.cleaned_data["last_name"],
                location=(location := self.cleaned_data["location"]),
                location_x_coordinate=(
                    self.cleaned_data["location_x_coordinate"] if location else None
                ),
                location_y_coordinate=(
                    self.cleaned_data["location_y_coordinate"] if location else None
                ),
            )
        return user


class RestaurantInfoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if "_hour_" in field_name:
                field.required = False

    def clean(self):
        super().clean()

        for day in (
            "sunday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
        ):
            if "open_hour_" + day not in self.cleaned_data:
                raise ValidationError(
                    f"The format of the opening hour for {day.capitalize()} is invalid."
                )

            if "close_hour_" + day not in self.cleaned_data:
                raise ValidationError(
                    f"The format of the closing hour for {day.capitalize()} is invalid."
                )

            if bool(self.cleaned_data["open_hour_" + day]) != bool(
                self.cleaned_data["close_hour_" + day]
            ):
                raise ValidationError(
                    "If you entered an opening time for a day of the week, make sure to also specify a closing time for said day."
                )

        if (location := self.cleaned_data.get("location")) != self.initial["location"]:
            try:
                match get_coordinates(location):
                    case (x, y):
                        self.cleaned_data["location_x_coordinate"] = x
                        self.cleaned_data["location_y_coordinate"] = y
                    case _:
                        raise ValidationError("Could not find location.")
            except GeopyError as e:
                raise ValidationError("Could not find location.") from e

    def save(self, commit=True):
        obj = super().save(False)
        if self.cleaned_data.get("location") != self.initial["location"]:
            obj.location_x_coordinate = self.cleaned_data["location_x_coordinate"]
            obj.location_y_coordinate = self.cleaned_data["location_y_coordinate"]
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Restaurant
        fields = (
            "description",
            "location",
            "open_hour_sunday",
            "close_hour_sunday",
            "open_hour_monday",
            "close_hour_monday",
            "open_hour_tuesday",
            "close_hour_tuesday",
            "open_hour_wednesday",
            "close_hour_wednesday",
            "open_hour_thursday",
            "close_hour_thursday",
            "open_hour_friday",
            "close_hour_friday",
            "open_hour_saturday",
            "close_hour_saturday",
        )

    # Django seems to have a bug where the TIME_INPUT_FORMATS setting is not
    # recognized, which makes it necessary to set the input format manually.
    open_hour_sunday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    close_hour_sunday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    open_hour_monday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    close_hour_monday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    open_hour_tuesday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    close_hour_tuesday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    open_hour_wednesday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    close_hour_wednesday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    open_hour_thursday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    close_hour_thursday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    open_hour_friday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    close_hour_friday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    open_hour_saturday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    close_hour_saturday = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )


class RegularAccountDetailsForm(forms.ModelForm):
    class Meta:
        model = CustomerInfo
        fields = ("first_name", "last_name", "location")

    location = forms.CharField(
        label="Your location (optional)", max_length=300, required=False
    )

    def clean(self):
        super().clean()
        location = self.cleaned_data.get("location", "").strip()
        if location and location != self.initial["location"]:
            try:
                match get_coordinates(location):
                    case (x, y):
                        self.cleaned_data["location_x_coordinate"] = x
                        self.cleaned_data["location_y_coordinate"] = y
                    case _:
                        raise ValidationError("Could not find location.")
            except GeopyError as e:
                raise ValidationError("Could not find location.") from e
        # If the user leaves the location field blank.
        elif not location:
            self.cleaned_data["location_x_coordinate"] = None
            self.cleaned_data["location_y_coordinate"] = None

    def save(self, commit=True):
        obj = super().save(False)
        if self.cleaned_data.get("location", "").strip() != self.initial["location"]:
            obj.location_x_coordinate = self.cleaned_data["location_x_coordinate"]
            obj.location_y_coordinate = self.cleaned_data["location_y_coordinate"]
        if commit:
            obj.save()
        return obj


class DeliveryAccountDetailsForm(forms.ModelForm):
    class Meta:
        model = DeliveryContractorInfo
        fields = ("first_name", "last_name", "location")

    def clean(self):
        super().clean()

        if (location := self.cleaned_data.get("location")) != self.initial["location"]:
            try:
                match get_coordinates(location):
                    case (x, y):
                        self.cleaned_data["location_x_coordinate"] = x
                        self.cleaned_data["location_y_coordinate"] = y
                    case _:
                        raise ValidationError("Could not find location.")
            except GeopyError as e:
                raise ValidationError("Could not find location.") from e

    def save(self, commit=True):
        obj = super().save(False)
        if self.cleaned_data.get("location") != self.initial["location"]:
            obj.location_x_coordinate = self.cleaned_data["location_x_coordinate"]
            obj.location_y_coordinate = self.cleaned_data["location_y_coordinate"]
        if commit:
            obj.save()
        return obj


class CreateOrderItemForm(forms.ModelForm):
    quantity = forms.IntegerField(min_value=1)

    class Meta:
        model = OrderItem
        fields = ("quantity",)


class OrdersWithinDistanceForm(forms.Form):
    max_distance = forms.IntegerField(label="Maximum distance (in miles)", min_value=1)


class OrdersWithStatusForm(forms.Form):
    status = forms.TypedChoiceField(
        choices=(
            ("Pl", "Placed"),
            ("Rp", "Ready to be picked up for delivery"),
            ("It", "In transit"),
            ("De", "Delivered"),
        ),
        coerce=Order.OrderStatus,
        empty_value="------",
    )


class TableForm(forms.ModelForm):
    local_id = forms.IntegerField(label="Table number")
    capacity = forms.IntegerField(label="Number of seats", min_value=1)

    class Meta:
        model = Table
        fields = ("local_id", "capacity")


class CreateReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ("number_of_guests",)

    date = forms.DateField(widget=forms.SelectDateWidget())
    time = forms.TimeField(
        input_formats=("%I:%M %p",), widget=forms.TimeInput(format="%I:%M %p")
    )
    minutes = forms.IntegerField(min_value=1)

    def __init__(self, *args, **kwargs):
        self.restaurant: Restaurant = kwargs.pop("restaurant")
        super().__init__(*args, **kwargs)

    def clean(self):
        start_date = datetime.combine(
            date=self.cleaned_data["date"], time=self.cleaned_data["time"]
        )
        end_date = start_date + timedelta(minutes=self.cleaned_data["minutes"])

        errors = []

        if start_date.date() < datetime_now().date():
            errors.append("Date must be today or in the future.")

        match start_date.weekday():
            case 0:
                if self.restaurant.open_hour_monday is None:
                    errors.append("Restaurant is closed on Mondays.")
                else:
                    if start_date.time() < self.restaurant.open_hour_monday:
                        errors.append(
                            "Reservation should not start before the opening hour on Monday."
                        )
                    if (
                        end_date.time() > self.restaurant.close_hour_monday
                        or start_date.date() != end_date.date()
                    ):
                        errors.append(
                            "Reservation should not extend past the closing hour on Monday."
                        )
            case 1:
                if self.restaurant.open_hour_tuesday is None:
                    errors.append("Restaurant is closed on Tuesdays.")
                else:
                    if start_date.time() < self.restaurant.open_hour_monday:
                        errors.append(
                            "Reservation should not start before the opening hour on Tuesday."
                        )
                    if (
                        end_date.time() > self.restaurant.close_hour_monday
                        or start_date.date() != end_date.date()
                    ):
                        errors.append(
                            "Reservation should not extend past the closing hour on Tuesday."
                        )
            case 2:
                if self.restaurant.open_hour_wednesday is None:
                    errors.append("Restaurant is closed on Wednesdays.")
                else:
                    if start_date.time() < self.restaurant.open_hour_monday:
                        errors.append(
                            "Reservation should not start before the opening hour on Wednesday."
                        )
                    if (
                        end_date.time() > self.restaurant.close_hour_monday
                        or start_date.date() != end_date.date()
                    ):
                        errors.append(
                            "Reservation should not extend past the closing hour on Wednesday."
                        )
            case 3:
                if self.restaurant.open_hour_thursday is None:
                    errors.append("Restaurant is closed on Thursdays.")
                else:
                    if start_date.time() < self.restaurant.open_hour_monday:
                        errors.append(
                            "Reservation should not start before the opening hour on Thursday."
                        )
                    if (
                        end_date.time() > self.restaurant.close_hour_monday
                        or start_date.date() != end_date.date()
                    ):
                        errors.append(
                            "Reservation should not extend past the closing hour on Thursday."
                        )
            case 4:
                if self.restaurant.open_hour_friday is None:
                    errors.append("Restaurant is closed on Fridays.")
                else:
                    if start_date.time() < self.restaurant.open_hour_monday:
                        errors.append(
                            "Reservation should not start before the opening hour on Friday."
                        )
                    if (
                        end_date.time() > self.restaurant.close_hour_monday
                        or start_date.date() != end_date.date()
                    ):
                        errors.append(
                            "Reservation should not extend past the closing hour on Friday."
                        )
            case 5:
                if self.restaurant.open_hour_saturday is None:
                    errors.append("Restaurant is closed on Saturdays.")
                else:
                    if start_date.time() < self.restaurant.open_hour_monday:
                        errors.append(
                            "Reservation should not start before the opening hour on Saturday."
                        )
                    if (
                        end_date.time() > self.restaurant.close_hour_monday
                        or start_date.date() != end_date.date()
                    ):
                        errors.append(
                            "Reservation should not extend past the closing hour on Saturday."
                        )
            case 6:
                if self.restaurant.open_hour_sunday is None:
                    errors.append("Restaurant is closed on Sundays.")
                else:
                    if start_date.time() < self.restaurant.open_hour_monday:
                        errors.append(
                            "Reservation should not start before the opening hour on Sunday."
                        )
                    if (
                        end_date.time() > self.restaurant.close_hour_monday
                        or start_date.date() != end_date.date()
                    ):
                        errors.append(
                            "Reservation should not extend past the closing hour on Sunday."
                        )

        if errors:
            raise ValidationError(errors)

        self.cleaned_data |= {"start_date": start_date, "end_date": end_date}


class ReservationsFilteringForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ("status",)

    date = forms.DateField(required=False, widget=forms.SelectDateWidget())


class TableModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"#{obj.local_id} ({obj.capacity} seats)"


class ModifyReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ("status", "table")

    table = TableModelChoiceField(required=False, queryset=None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        reservation = self.instance

        self.fields["table"].queryset = (
            Table.objects.filter(
                restaurant=reservation.restaurant,
                capacity__gte=reservation.number_of_guests,
            )
            # Excludes all tables that have reservations whose start and end times
            # overlap with this reservation. The tilde Q object is used so that this
            # reservation is not included in the exclusion, thus allowing its table
            # (if it already has a table associated with it) to be one of the choices.
            .exclude(
                ~Q(reservations__id=reservation.id),
                reservations__start_date__lte=reservation.end_date,
                reservations__end_date__gte=reservation.start_date,
            )
        )
