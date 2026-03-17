# UNO Overlays Format UI Elements

This document describes the UI elements that need to be added to `mainwindow.ui` to support the UNO overlays format feature.

## Required UI Elements

The following UI elements need to be added to the UNO tab in the mainwindow.ui file using Qt Designer:

### 1. Overlays Format Checkbox
- **Widget Type:** QCheckBox
- **Object Name:** `checkBox_uno_overlays_format`
- **Text:** "Overlays Format"
- **Location:** Should be placed in the `widget_26` section (row 1440-1520 in mainwindow.ui), alongside the existing checkboxes (Send Same?, Essentials)
- **Purpose:** Toggle between standard UNO format (PUT with individual commands) and overlays format (PATCH with batched updates)

### 2. SubComposition ID Label
- **Widget Type:** QLabel
- **Object Name:** `label_uno_subcomposition_id` (or similar)
- **Text:** "SubComposition ID"
- **Purpose:** Label for the subCompositionId input field

### 3. SubComposition ID Input
- **Widget Type:** QLineEdit
- **Object Name:** `lineEdit_uno_subcomposition_id`
- **Placeholder Text:** "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
- **Purpose:** Input field for the overlay's subCompositionId

### 4. Overlays Details Container Widget
- **Widget Type:** QWidget
- **Object Name:** `widget_uno_overlays_details`
- **Layout:** QHBoxLayout
- **Purpose:** Container widget that holds the SubComposition ID label and input field. This widget will be shown/hidden based on the overlays format checkbox state.

## Recommended Layout Structure

The elements should be added to the UNO tab section, following the pattern used for the Essentials feature:

```xml
<item>
 <widget class="QWidget" name="widget_26" native="true">
  <layout class="QHBoxLayout" name="horizontalLayout_30">
   <!-- Existing checkboxes -->
   <item>
    <widget class="QCheckBox" name="checkBox_uno_send_same">...</widget>
   </item>
   <item>
    <widget class="QCheckBox" name="checkBox_uno_essentials">...</widget>
   </item>

   <!-- NEW: Add Overlays Format checkbox here -->
   <item>
    <widget class="QCheckBox" name="checkBox_uno_overlays_format">
     <property name="text">
      <string>Overlays Format</string>
     </property>
    </widget>
   </item>

   <!-- Existing rate limit controls -->
  </layout>
 </widget>
</item>

<!-- NEW: Add after widget_uno_essentials_details (around line 1568) -->
<item>
 <widget class="QWidget" name="widget_uno_overlays_details" native="true">
  <layout class="QHBoxLayout" name="horizontalLayout_uno_overlays">
   <property name="leftMargin"><number>0</number></property>
   <property name="topMargin"><number>0</number></property>
   <property name="rightMargin"><number>0</number></property>
   <property name="bottomMargin"><number>0</number></property>

   <item>
    <widget class="QLabel" name="label_uno_subcomposition_id">
     <property name="text">
      <string>SubComposition ID</string>
     </property>
    </widget>
   </item>

   <item>
    <widget class="QLineEdit" name="lineEdit_uno_subcomposition_id">
     <property name="placeholderText">
      <string>aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
</item>
```

## Behavior

1. **Default State:** The overlays format checkbox should be unchecked by default, maintaining backward compatibility with existing UNO integrations.

2. **Visibility Toggle:** When the overlays format checkbox is checked:
   - The `widget_uno_overlays_details` container becomes visible
   - The Essentials checkbox becomes disabled and unchecked (overlays format and essentials are not compatible)

3. **When Disabled:** When the overlays format checkbox is unchecked:
   - The `widget_uno_overlays_details` container becomes hidden
   - The Essentials checkbox becomes enabled again

## Alternative: Running Without UI Elements

If the UI elements are not added to mainwindow.ui, the overlays format feature can still be used programmatically by:

1. Manually editing the `scoresight.json` configuration file
2. Setting the following values:
   ```json
   {
     "uno_overlays_format": true,
     "uno_subcomposition_id": "your-overlay-uuid-here"
   }
   ```

The code includes checks using `hasattr()` to gracefully handle the absence of UI elements, with debug logging to indicate when UI elements are not found.

## Testing

After adding the UI elements:

1. Open ScoreSight and go to the UNO tab
2. Verify the "Overlays Format" checkbox is present
3. Check the checkbox - the SubComposition ID field should appear
4. Verify the Essentials checkbox becomes disabled
5. Uncheck the Overlays Format checkbox - the SubComposition ID field should hide
6. Verify the Essentials checkbox becomes enabled again
7. Enter a subComposition ID and ensure it's saved to storage
8. Enable UNO updates and verify that PATCH requests are sent with the correct batched format

## Field Mapping Differences

**Standard Format (PUT):**
- Maps to command names: `"Home Score": "SetGoalsHome"`
- Each field sends individual PUT request
- Format: `{"command": "SetGoalsHome", "value": "35"}`

**Overlays Format (PATCH):**
- Maps to field names: `"Home Score": "Team 1 Score"`
- All fields batched into single PATCH request
- Format: `[{"subCompositionId": "uuid", "payload": {"Team 1 Score": "35", "Team 2 Score": "22"}}]`

When using overlays format, ensure field mappings use the actual field names as they appear in the overlay composition, not command names.
