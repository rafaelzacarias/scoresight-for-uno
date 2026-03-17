# UNO Overlays Format - Usage Examples

## Example 1: Basketball Scoreboard

### Standard Format (Current)
```json
{
  "uno_overlays_format": false,
  "uno_mapping": {
    "Home Score": "SetGoalsHome",
    "Away Score": "SetGoalsAway",
    "Time": "SetMatchTime",
    "Period": "SetPeriod"
  }
}
```

**Requests sent:**
```http
PUT /apiv2/controlapps/.../api
Content-Type: application/json

{"command": "SetGoalsHome", "value": "78"}
```
```http
PUT /apiv2/controlapps/.../api
Content-Type: application/json

{"command": "SetGoalsAway", "value": "72"}
```
*(4 separate PUT requests, one per field)*

### Overlays Format (New)
```json
{
  "uno_overlays_format": true,
  "uno_subcomposition_id": "12345678-1234-1234-1234-123456789abc",
  "uno_mapping": {
    "Home Score": "Team 1 Score",
    "Away Score": "Team 2 Score",
    "Time": "ocrClock",
    "Period": "Period"
  }
}
```

**Request sent:**
```http
PATCH /apiv2/controlapps/.../api
Content-Type: application/json

[
  {
    "subCompositionId": "12345678-1234-1234-1234-123456789abc",
    "payload": {
      "Team 1 Score": "78",
      "Team 2 Score": "72",
      "ocrClock": "3:45",
      "Period": "Q4"
    }
  }
]
```
*(1 batched PATCH request with all fields)*

## Example 2: Soccer/Football Match

### Standard Format
```json
{
  "uno_overlays_format": false,
  "uno_mapping": {
    "Home Team": "SetTeamHome",
    "Away Team": "SetTeamAway",
    "Home Goals": "SetGoalsHome",
    "Away Goals": "SetGoalsAway",
    "Match Time": "SetMatchTime"
  }
}
```

### Overlays Format
```json
{
  "uno_overlays_format": true,
  "uno_subcomposition_id": "abcdef12-3456-7890-abcd-ef1234567890",
  "uno_mapping": {
    "Home Team": "homeTeamName",
    "Away Team": "awayTeamName",
    "Home Goals": "homeScore",
    "Away Goals": "awayScore",
    "Match Time": "matchClock"
  }
}
```

**PATCH Request:**
```json
[
  {
    "subCompositionId": "abcdef12-3456-7890-abcd-ef1234567890",
    "payload": {
      "homeTeamName": "Manchester United",
      "awayTeamName": "Liverpool",
      "homeScore": "2",
      "awayScore": "1",
      "matchClock": "67:32"
    }
  }
]
```

## Example 3: Ice Hockey

### Overlays Format Configuration
```json
{
  "uno_overlays_format": true,
  "uno_subcomposition_id": "hockey-uuid-here",
  "uno_send_same": false,
  "uno_mapping": {
    "Home Score": "Home Score",
    "Away Score": "Away Score",
    "Period": "Period Text",
    "Time": "Game Clock",
    "Home SOG": "Home Shots",
    "Away SOG": "Away Shots"
  }
}
```

**PATCH Request:**
```json
[
  {
    "subCompositionId": "hockey-uuid-here",
    "payload": {
      "Home Score": "4",
      "Away Score": "3",
      "Period Text": "3rd",
      "Game Clock": "15:42",
      "Home Shots": "28",
      "Away Shots": "31"
    }
  }
]
```

## How to Get Your subCompositionId

1. Open your overlay in overlays.uno editor
2. Inspect the overlay's composition settings
3. Look for the subComposition or overlay UUID
4. Copy the UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
5. Paste it into the ScoreSight UNO settings

Alternatively, check the scoreboard-ocr documentation for your specific overlay configuration.

## Switching Between Formats

You can switch between formats at any time:

### To Enable Overlays Format:
1. Check "Overlays Format" in UNO tab
2. Enter your subCompositionId
3. Update field mappings to use field names (not commands)
4. Click the UNO toggle to restart with new settings

### To Disable Overlays Format:
1. Uncheck "Overlays Format" in UNO tab
2. Update field mappings to use command names (e.g., SetGoalsHome)
3. Click the UNO toggle to restart with standard format

## Benefits of Overlays Format

1. **Reduced Network Traffic**: One request instead of multiple
2. **Atomic Updates**: All fields update together, no partial states
3. **Better Performance**: Less overhead, faster updates
4. **Scoreboard-OCR Compatible**: Works with existing scoreboard-ocr configurations
5. **Cleaner Logs**: Single batch logged instead of multiple individual sends

## Compatibility

### Works With:
- overlays.uno PATCH endpoint
- scoreboard-ocr format overlays
- Custom overlays with subComposition support
- All existing ScoreSight features (OCR, detection, etc.)

### Does Not Work With:
- UNO Essentials mode (mutually exclusive)
- Standard UNO command-based overlays (use standard format instead)

## Troubleshooting

### "subCompositionId is not set" Error
**Solution**: Enter your overlay's subCompositionId in the text field

### Fields Not Updating
**Solution**: Verify field names match your overlay's field names exactly (case-sensitive)

### 404 or 400 Errors
**Solution**:
- Check that your UNO endpoint URL is correct
- Verify your overlay supports PATCH requests
- Confirm subCompositionId is valid

### Fields Update Individually Instead of Batched
**Solution**: Verify "Overlays Format" checkbox is checked and saved

## Performance Comparison

### Standard Format:
- 5 fields = 5 HTTP requests
- ~50-100ms total (10-20ms per request)
- Network overhead per field

### Overlays Format:
- 5 fields = 1 HTTP request
- ~10-20ms total
- Single network overhead
- 70-80% reduction in request time

## Field Naming Guidelines

When using overlays format, field names should:
- Match your overlay's field names exactly
- Be descriptive (e.g., "Team 1 Score" not "T1S")
- Use consistent naming (e.g., all "Score" or all "Goals")
- Follow your overlay designer's naming convention

Common field name patterns:
- Scores: "Team 1 Score", "Team 2 Score", "homeScore", "awayScore"
- Time: "ocrClock", "Game Clock", "matchTime", "Clock"
- Period: "Period", "Quarter", "Half", "Period Text"
- Teams: "homeTeamName", "awayTeamName", "Home Team", "Away Team"
