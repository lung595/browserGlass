import QtQuick

// DMS's ListSettingWithInput: a ListSetting with one input per field. A test
// fills the inputs and presses Add with submit(["value for field 0", ...]),
// which follows the real Add button: trimmed values, a required field left
// empty or all fields empty add nothing, an empty field takes its default.
ListSetting {
    id: root

    property var fields: []

    function submit(values) {
        const item = {};
        let hasValue = false;
        for (let i = 0; i < fields.length; i++) {
            const field = fields[i];
            const value = String(values[i] === undefined ? "" : values[i]).trim();
            if (value !== "")
                hasValue = true;
            if (field.required && value === "")
                return false;
            item[field.id] = value || (field.default || "");
        }
        if (!hasValue)
            return false;
        addItem(item);
        return true;
    }
}
