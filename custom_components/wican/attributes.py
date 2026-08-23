from dataclasses import dataclass, field

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory


@dataclass
class WiCANBinarySensorEntityDescription(BinarySensorEntityDescription):
    extra_attributes: list[str] | None = field(default_factory=list)

@dataclass
class WiCANSensorEntityDescription(SensorEntityDescription):
    extra_attributes: list[str] | None = field(default_factory=list)

SENSOR_DESCRIPTIONS: tuple[WiCANSensorEntityDescription, ...] = (
    WiCANSensorEntityDescription(
        key="wifi_mode",
        translation_key="wifi_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
        extra_attributes=[
            "ap_ch",
            "ap_auto_disable",
            "sta_status",
            "mdns",
        ],
    ),
    WiCANSensorEntityDescription(
        # Not EntityCategory.DIAGNOSTIC: this is the car's 12V battery, a primary
        # reading alongside HV state of charge and temperature, not device health.
        key="batt_voltage",
        translation_key="batt_voltage",
        icon="mdi:car-battery",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="V",
        suggested_display_precision=1,
        extra_attributes=[
            "batt_alert",
            "batt_alert_volt",
            "batt_alert_protocol",
            "batt_alert_topic",
            "batt_alert_time",
        ],
    ),
    WiCANSensorEntityDescription(
        key="battery_soc_pct",
        translation_key="battery_soc_pct",
        icon="mdi:battery-charging-high",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        suggested_display_precision=1,
        extra_attributes=[
            "battery_soc_valid",
            "battery_soc_age_ms",
        ],
    ),
    WiCANSensorEntityDescription(
        key="battery_temp_min_c",
        translation_key="battery_temp_min_c",
        icon="mdi:thermometer-low",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        suggested_display_precision=0,
        extra_attributes=[
            "battery_temp_valid",
            "battery_temp_age_ms",
        ],
    ),
    WiCANSensorEntityDescription(
        key="battery_temp_max_c",
        translation_key="battery_temp_max_c",
        icon="mdi:thermometer-high",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        suggested_display_precision=0,
        extra_attributes=[
            "battery_temp_valid",
            "battery_temp_age_ms",
        ],
    ),
    WiCANSensorEntityDescription(
        key="vpn_status",
        translation_key="vpn_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:shield-key",
        extra_attributes=[
            "vpn_ip",
        ],
    ),
    WiCANSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
    ),
)

BINARY_SENSOR_DESCRIPTIONS: tuple[WiCANBinarySensorEntityDescription, ...] = (
    WiCANBinarySensorEntityDescription(
        # Decoded from the low nibble of byte 0 of CAN frame 0x038.
        key="car_ready",
        translation_key="car_ready",
        icon="mdi:car-electric",
        device_class=BinarySensorDeviceClass.RUNNING,
        extra_attributes=[
            "car_power_state",
            "car_power_raw",
            "car_power_age_ms",
        ],
    ),
    WiCANBinarySensorEntityDescription(
        key="ble_status",
        translation_key="ble_status",
        icon="mdi:bluetooth",
        entity_category=EntityCategory.DIAGNOSTIC,
        extra_attributes=[
            "ble_power",
        ],
    ),
    WiCANBinarySensorEntityDescription(
        key="ecu_status",
        translation_key="ecu_status",
        icon="mdi:car-connected",
        entity_category=EntityCategory.DIAGNOSTIC,
        extra_attributes=[
            "obd_chip_status",
        ],
    ),
)

def get_sensor_attributes(entity_description, data: dict) -> dict:
    status = data.get("status", {})
    attrs = {}
    for attr_key in getattr(entity_description, "extra_attributes", []):
        if status.get(attr_key) is not None:
            attrs[attr_key] = status[attr_key]
    return attrs

