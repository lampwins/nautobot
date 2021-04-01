import re
from collections import OrderedDict
from datetime import datetime, date

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import RegexValidator, ValidationError
from django.db import models
from django.utils.safestring import mark_safe

from nautobot.extras.choices import *
from nautobot.extras.tasks import delete_custom_field_data, update_custom_field_choice_data
from nautobot.extras.utils import FeatureQuery
from nautobot.core.models import BaseModel
from nautobot.utilities.fields import JSONArrayField
from nautobot.utilities.forms import (
    CSVChoiceField,
    CSVMultipleChoiceField,
    DatePicker,
    LaxURLField,
    StaticSelect2,
    StaticSelect2Multiple,
    add_blank_choice,
)
from nautobot.utilities.querysets import RestrictedQuerySet
from nautobot.utilities.validators import validate_regex


class CustomFieldModel(models.Model):
    """
    Abstract class for any model which may have custom fields associated with it.
    """

    custom_field_data = models.JSONField(encoder=DjangoJSONEncoder, blank=True, default=dict)

    class Meta:
        abstract = True

    @property
    def cf(self):
        """
        Convenience wrapper for custom field data.
        """
        return self.custom_field_data

    def get_custom_fields(self):
        """
        Return a dictionary of custom fields for a single object in the form {<field>: value}.
        """
        fields = CustomField.objects.get_for_model(self)
        return OrderedDict([(field, self.custom_field_data.get(field.name)) for field in fields])

    def clean(self):
        super().clean()

        custom_fields = {cf.name: cf for cf in CustomField.objects.get_for_model(self)}

        # Validate all field values
        for field_name, value in self.custom_field_data.items():
            if field_name not in custom_fields:
                raise ValidationError(f"Unknown field name '{field_name}' in custom field data.")
            try:
                custom_fields[field_name].validate(value)
            except ValidationError as e:
                raise ValidationError(f"Invalid value for custom field '{field_name}': {e.message}")

        # Check for missing required values
        for cf in custom_fields.values():
            if cf.required and cf.name not in self.custom_field_data:
                raise ValidationError(f"Missing required custom field '{cf.name}'.")


class CustomFieldManager(models.Manager.from_queryset(RestrictedQuerySet)):
    use_in_migrations = True

    def get_for_model(self, model):
        """
        Return all CustomFields assigned to the given model.
        """
        content_type = ContentType.objects.get_for_model(model._meta.concrete_model)
        return self.get_queryset().filter(content_types=content_type)


class CustomField(BaseModel):
    content_types = models.ManyToManyField(
        to=ContentType,
        related_name="custom_fields",
        verbose_name="Object(s)",
        limit_choices_to=FeatureQuery("custom_fields"),
        help_text="The object(s) to which this field applies.",
    )
    type = models.CharField(
        max_length=50,
        choices=CustomFieldTypeChoices,
        default=CustomFieldTypeChoices.TYPE_TEXT,
    )
    name = models.CharField(max_length=50, unique=True, help_text="Internal field name")
    label = models.CharField(
        max_length=50,
        blank=True,
        help_text="Name of the field as displayed to users (if not provided, " "the field's name will be used)",
    )
    description = models.CharField(max_length=200, blank=True)
    required = models.BooleanField(
        default=False,
        help_text="If true, this field is required when creating new objects " "or editing an existing object.",
    )
    filter_logic = models.CharField(
        max_length=50,
        choices=CustomFieldFilterLogicChoices,
        default=CustomFieldFilterLogicChoices.FILTER_LOOSE,
        help_text="Loose matches any instance of a given string; exact " "matches the entire field.",
    )
    default = models.JSONField(
        encoder=DjangoJSONEncoder,
        blank=True,
        null=True,
        help_text="Default value for the field (must be a JSON value). Encapsulate "
        'strings with double quotes (e.g. "Foo").',
    )
    weight = models.PositiveSmallIntegerField(
        default=100, help_text="Fields with higher weights appear lower in a form."
    )
    validation_minimum = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Minimum value",
        help_text="Minimum allowed value (for numeric fields)",
    )
    validation_maximum = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Maximum value",
        help_text="Maximum allowed value (for numeric fields)",
    )
    validation_regex = models.CharField(
        blank=True,
        validators=[validate_regex],
        max_length=500,
        verbose_name="Validation regex",
        help_text="Regular expression to enforce on text field values. Use ^ and $ to force matching of entire string. "
        "For example, <code>^[A-Z]{3}$</code> will limit values to exactly three uppercase letters.",
    )

    objects = CustomFieldManager()

    class Meta:
        ordering = ["weight", "name"]

    def __str__(self):
        return self.label or self.name.replace("_", " ").capitalize()

    def clean(self):
        super().clean()

        if self.present_in_database:
            # Check immutable fields
            database_object = self.__class__.objects.get(pk=self.pk)

            if self.name != database_object.name:
                raise ValidationError({"name": "Name cannot be changed once created"})

            if self.type != database_object.type:
                raise ValidationError({"type": "Type cannot be changed once created"})

        # Validate the field's default value (if any)
        if self.default is not None:
            try:
                self.validate(self.default)
            except ValidationError as err:
                raise ValidationError({"default": f'Invalid default value "{self.default}": {err.message}'})

        # Minimum/maximum values can be set only for numeric fields
        if self.validation_minimum is not None and self.type != CustomFieldTypeChoices.TYPE_INTEGER:
            raise ValidationError({"validation_minimum": "A minimum value may be set only for numeric fields"})
        if self.validation_maximum is not None and self.type != CustomFieldTypeChoices.TYPE_INTEGER:
            raise ValidationError({"validation_maximum": "A maximum value may be set only for numeric fields"})

        # Regex validation can be set only for text fields
        regex_types = (
            CustomFieldTypeChoices.TYPE_TEXT,
            CustomFieldTypeChoices.TYPE_URL,
        )
        if self.validation_regex and self.type not in regex_types:
            raise ValidationError(
                {"validation_regex": "Regular expression validation is supported only for text and URL fields"}
            )

        # Choices can be set only on selection fields
        if self.choices.exists() and self.type not in (
            CustomFieldTypeChoices.TYPE_SELECT,
            CustomFieldTypeChoices.TYPE_MULTISELECT,
        ):
            raise ValidationError("Choices may be set only for custom selection fields.")

        # A selection field's default (if any) must be present in its available choices
        if (
            self.type == CustomFieldTypeChoices.TYPE_SELECT
            and self.default
            and self.default not in self.choices.values_list("value", flat=True)
        ):
            raise ValidationError(
                {"default": f"The specified default value ({self.default}) is not listed as an available choice."}
            )

    def to_form_field(self, set_initial=True, enforce_required=True, for_csv_import=False):
        """
        Return a form field suitable for setting a CustomField's value for an object.

        set_initial: Set initial date for the field. This should be False when generating a field for bulk editing.
        enforce_required: Honor the value of CustomField.required. Set to False for filtering/bulk editing.
        for_csv_import: Return a form field suitable for bulk import of objects in CSV format.
        """
        initial = self.default if set_initial else None
        required = self.required if enforce_required else False

        # Integer
        if self.type == CustomFieldTypeChoices.TYPE_INTEGER:
            field = forms.IntegerField(
                required=required,
                initial=initial,
                min_value=self.validation_minimum,
                max_value=self.validation_maximum,
            )

        # Boolean
        elif self.type == CustomFieldTypeChoices.TYPE_BOOLEAN:
            choices = (
                (None, "---------"),
                (True, "True"),
                (False, "False"),
            )
            field = forms.NullBooleanField(
                required=required,
                initial=initial,
                widget=StaticSelect2(choices=choices),
            )

        # Date
        elif self.type == CustomFieldTypeChoices.TYPE_DATE:
            field = forms.DateField(required=required, initial=initial, widget=DatePicker())

        # URL
        elif self.type == CustomFieldTypeChoices.TYPE_URL:
            field = LaxURLField(required=required, initial=initial)

        # Text
        elif self.type == CustomFieldTypeChoices.TYPE_TEXT:
            field = forms.CharField(max_length=255, required=required, initial=initial)
            if self.validation_regex:
                field.validators = [
                    RegexValidator(
                        regex=self.validation_regex,
                        message=mark_safe(f"Values must match this regex: <code>{self.validation_regex}</code>"),
                    )
                ]

        # Select or Multi-select
        else:
            choices = [(cfc.value, cfc.value) for cfc in self.choices.all()]
            default_choice = self.choices.filter(value=self.default).first()

            if not required or default_choice is None:
                choices = add_blank_choice(choices)

            # Set the initial value to the first available choice (if any)
            if set_initial and default_choice:
                initial = default_choice.value

            if self.type == CustomFieldTypeChoices.TYPE_SELECT:
                field_class = CSVChoiceField if for_csv_import else forms.ChoiceField
                field = field_class(
                    choices=choices,
                    required=required,
                    initial=initial,
                    widget=StaticSelect2(),
                )
            else:
                field_class = CSVMultipleChoiceField if for_csv_import else forms.MultipleChoiceField
                field = field_class(choices=choices, required=required, initial=initial, widget=StaticSelect2Multiple())

        field.model = self
        field.label = str(self)
        if self.description:
            field.help_text = self.description

        return field

    def validate(self, value):
        """
        Validate a value according to the field's type validation rules.
        """
        if value not in [None, "", []]:

            # Validate text field
            if self.type == CustomFieldTypeChoices.TYPE_TEXT and self.validation_regex:
                if not re.match(self.validation_regex, value):
                    raise ValidationError(f"Value must match regex '{self.validation_regex}'")

            # Validate integer
            if self.type == CustomFieldTypeChoices.TYPE_INTEGER:
                try:
                    int(value)
                except ValueError:
                    raise ValidationError("Value must be an integer.")
                if self.validation_minimum is not None and value < self.validation_minimum:
                    raise ValidationError(f"Value must be at least {self.validation_minimum}")
                if self.validation_maximum is not None and value > self.validation_maximum:
                    raise ValidationError(f"Value must not exceed {self.validation_maximum}")

            # Validate boolean
            if self.type == CustomFieldTypeChoices.TYPE_BOOLEAN and value not in [
                True,
                False,
                1,
                0,
            ]:
                raise ValidationError("Value must be true or false.")

            # Validate date
            if self.type == CustomFieldTypeChoices.TYPE_DATE:
                if type(value) is not date:
                    try:
                        datetime.strptime(value, "%Y-%m-%d")
                    except ValueError:
                        raise ValidationError("Date values must be in the format YYYY-MM-DD.")

            # Validate selected choice
            if self.type == CustomFieldTypeChoices.TYPE_SELECT:
                if value not in self.choices.values_list("value", flat=True):
                    raise ValidationError(
                        f"Invalid choice ({value}). Available choices are: {', '.join(self.choices.values_list('value', flat=True))}"
                    )

            if self.type == CustomFieldTypeChoices.TYPE_MULTISELECT:
                if not set(value).issubset(self.choices.values_list("value", flat=True)):
                    raise ValidationError(
                        f"Invalid choice(s) ({value}). Available choices are: {', '.join(self.choices.values_list('value', flat=True))}"
                    )

        elif self.required:
            raise ValidationError("Required field cannot be empty.")

    def delete(self, *args, **kwargs):
        """
        Handle the cleanup of old custom field data when a CustomField is deleted.
        """
        content_types = set(self.content_types.values_list("pk", flat=True))

        super().delete(*args, **kwargs)

        delete_custom_field_data.delay(self.name, content_types)


class CustomFieldChoice(BaseModel):
    """
    The custom field choice is used to store the possible set of values for a selection type custom field
    """

    field = models.ForeignKey(
        to="extras.CustomField",
        on_delete=models.CASCADE,
        related_name="choices",
        limit_choices_to=models.Q(
            type__in=[CustomFieldTypeChoices.TYPE_SELECT, CustomFieldTypeChoices.TYPE_MULTISELECT]
        ),
    )
    value = models.CharField(max_length=100)
    weight = models.PositiveSmallIntegerField(default=100, help_text="Higher weights appear later in the list")

    class Meta:
        ordering = ["field", "weight", "value"]
        unique_together = ["field", "value"]

    def __str__(self):
        return self.value

    def clean(self):
        if self.field.type not in (CustomFieldTypeChoices.TYPE_SELECT, CustomFieldTypeChoices.TYPE_MULTISELECT):
            raise ValidationError("Custom field choices can only be assigned to selection fields.")

    def save(self, *args, **kwargs):
        """
        When a custom field choice is saved, perform logic that will update data across all custom field data.
        """
        if self.present_in_database:
            database_object = self.__class__.objects.get(pk=self.pk)
        else:
            database_object = self

        super().save(*args, **kwargs)

        if self.value != database_object.value:
            update_custom_field_choice_data.delay(self.field.pk, database_object.value, self.value)

    def delete(self, *args, **kwargs):
        """
        When a custom field choice is deleted, remove references to in custom field data
        """
        if self.field.default:
            # Cannot delete the choice if it is the default value.
            if self.field.type == CustomFieldTypeChoices.TYPE_SELECT and self.field.default == self.value:
                raise models.ProtectedError(
                    self, "Cannot delete this choice because it is the default value for the field."
                )
            elif self.value in self.field.default:
                raise models.ProtectedError(
                    self, "Cannot delete this choice because it is one of the default values for the field."
                )

        if self.field.type == CustomFieldTypeChoices.TYPE_SELECT:
            # Check if this value is in active use in a select field
            for ct in self.field.content_types.all():
                model = ct.model_class()
                if model.objects.filter(**{f"custom_field_data__{self.field.name}": self.value}).exists():
                    raise models.ProtectedError(self, "Cannot delete this choice because it is in active use.")

        else:
            # Check if this value is in active use in a multi-select field
            for ct in self.field.content_types.all():
                model = ct.model_class()
                if model.objects.filter(**{f"custom_field_data__{self.field.name}__contains": self.value}).exists():
                    raise models.ProtectedError(self, "Cannot delete this choice because it is in active use.")

        super().delete(*args, **kwargs)
