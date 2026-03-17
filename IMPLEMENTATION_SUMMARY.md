# UNO Overlays Format Implementation Summary

## Overview
This implementation adds support for the scoreboard-ocr compatible overlays format to ScoreSight's UNO integration. The new format uses PATCH requests with batched updates instead of individual PUT requests.

## Changes Made

### 1. `/home/runner/work/scoresight-for-uno/scoresight-for-uno/src/uno_output.py`

#### New Instance Variables (in `__init__`):
- `self.use_overlays_format` - Boolean flag to enable overlays format (default: False)
- `self.subCompositionId` - String containing the overlay's subComposition UUID

Both values are loaded from storage and subscribed to data changes:
```python
self.use_overlays_format = fetch_data("scoresight.json", "uno_overlays_format", False)
subscribe_to_data("scoresight.json", "uno_overlays_format", self.set_overlays_format)
self.subCompositionId = fetch_data("scoresight.json", "uno_subcomposition_id", "")
subscribe_to_data("scoresight.json", "uno_subcomposition_id", self.set_subcomposition_id)
```

#### New Setter Methods:
- `set_overlays_format(use_overlays_format)` - Updates the overlays format flag
- `set_subcomposition_id(subCompositionId)` - Updates the subComposition ID

#### Modified Method: `update_uno()`
The method now checks the `use_overlays_format` flag:
- **If True**: Collects all field updates into a dictionary and calls `send_uno_overlays_batch()`
- **If False**: Uses existing behavior (individual PUT requests via `send_uno_command()`)

#### New Method: `send_uno_overlays_batch(updates)`
Sends batched updates using the overlays format:
- **HTTP Method**: PATCH (not PUT)
- **Payload Format**:
  ```json
  [
    {
      "subCompositionId": "overlay-uuid",
      "payload": {
        "Team 1 Score": "35",
        "Team 2 Score": "22"
      }
    }
  ]
  ```
- **Error Handling**: Validates that `subCompositionId` is set before sending
- **Logging**: Debug logs for successful sends, error logs for failures
- **Rate Limiting**: Uses existing `check_rate_limits()` method

### 2. `/home/runner/work/scoresight-for-uno/scoresight-for-uno/src/uno_ui_handler.py`

#### Modified Method: `unoUiSetup()`
Added UI element connections for overlays format feature:
- Checks for `checkBox_uno_overlays_format` using `hasattr()`
- Loads overlays format setting from storage
- Connects checkbox to `set_uno_overlays_format()` handler
- Checks for `lineEdit_uno_subcomposition_id` and connects it to storage
- Shows/hides `widget_uno_overlays_details` based on checkbox state
- Includes graceful fallback with debug logging if UI elements are missing

#### New Method: `set_uno_overlays_format(value)`
Handles the overlays format checkbox state change:
- Saves the setting to storage via `globalSettingsChanged()`
- Shows/hides the `widget_uno_overlays_details` container
- **Mutual Exclusivity**: When overlays format is enabled:
  - Disables and unchecks the Essentials checkbox (they're not compatible)
  - When disabled, re-enables the Essentials checkbox

### 3. `/home/runner/work/scoresight-for-uno/scoresight-for-uno/UNO_OVERLAYS_UI_ELEMENTS.md`
Comprehensive documentation for adding UI elements via Qt Designer, including:
- Required UI element specifications
- Recommended XML structure
- Behavior descriptions
- Alternative configuration via JSON
- Testing procedures
- Field mapping differences

## Backward Compatibility

The implementation maintains full backward compatibility:
- **Default State**: Overlays format is disabled by default (`uno_overlays_format: False`)
- **Existing Behavior**: When disabled, uses existing PUT-based individual updates
- **Graceful Degradation**: Code checks for UI elements with `hasattr()` and logs when missing
- **No Breaking Changes**: Existing UNO integrations continue to work without any changes

## Key Features

### 1. Format Comparison

**Standard Format (Current):**
- HTTP Method: PUT
- Request per field: Individual
- Payload: `{"command": "SetGoalsHome", "value": "35"}`
- Field Mapping: Command names (e.g., "SetGoalsHome")

**Overlays Format (New):**
- HTTP Method: PATCH
- Request per field: Batched (all fields in one request)
- Payload: `[{"subCompositionId": "uuid", "payload": {"Team 1 Score": "35", ...}}]`
- Field Mapping: Field names (e.g., "Team 1 Score")

### 2. Mutual Exclusivity
- Overlays format and Essentials mode cannot be enabled simultaneously
- When overlays format is checked, Essentials is automatically disabled
- UI prevents conflicting configurations

### 3. Configuration Storage
Settings are stored in `scoresight.json`:
```json
{
  "uno_overlays_format": false,
  "uno_subcomposition_id": ""
}
```

### 4. Error Handling
- Validates `subCompositionId` is set before sending overlays batch
- Logs errors with descriptive messages
- Uses existing rate limit checking
- Graceful handling of missing UI elements

## Testing Recommendations

1. **Default Behavior Test**: Verify existing UNO integration still works without changes
2. **Enable Overlays**: Check the overlays format checkbox and verify UI updates
3. **Mutual Exclusivity**: Confirm Essentials gets disabled when overlays format is enabled
4. **Batch Requests**: Monitor network traffic to verify PATCH requests with batched payload
5. **Field Mapping**: Test with scoreboard-ocr field names instead of command names
6. **Storage Persistence**: Restart app and verify settings are saved/loaded correctly
7. **Missing UI Elements**: Test without UI elements to verify graceful degradation

## Usage Instructions

### With UI Elements:
1. Open ScoreSight and navigate to the UNO tab
2. Check the "Overlays Format" checkbox
3. Enter your overlay's subComposition ID in the text field
4. Map fields using scoreboard-ocr field names (e.g., "Team 1 Score", "ocrClock")
5. Enable UNO updates

### Without UI Elements (Manual Configuration):
1. Edit `scoresight.json` directly:
   ```json
   {
     "uno_overlays_format": true,
     "uno_subcomposition_id": "your-uuid-here"
   }
   ```
2. Map fields in the UI using field names instead of command names
3. Enable UNO updates

## Implementation Notes

- The code follows existing patterns in ScoreSight (storage subscriptions, logging, error handling)
- All new code includes comments explaining functionality
- Logging uses appropriate levels (debug for normal operation, error for failures)
- The implementation is defensive (checks before use, validates inputs)
- UI code gracefully handles missing elements for forward compatibility

## Next Steps

To complete the feature, the UI elements need to be added to `mainwindow.ui`:
1. Open `/home/runner/work/scoresight-for-uno/scoresight-for-uno/src/mainwindow.ui` in Qt Designer
2. Add the UI elements as specified in `UNO_OVERLAYS_UI_ELEMENTS.md`
3. Save the UI file
4. Regenerate Python UI bindings if needed
5. Test the feature end-to-end

Even without UI elements, the feature can be used via manual JSON configuration.
