import json
import threading
from datetime import datetime

import requests
from text_detection_target import TextDetectionTargetWithResult
from sc_logging import logger
from storage import subscribe_to_data, fetch_data


class UNOAPI:
    MAX_RESPONSE_LOG_LENGTH = 500

    def __init__(self, endpoint, field_mapping):
        self.endpoint = endpoint
        self.field_mapping = field_mapping
        self.running = False
        self._log_callback = None
        self.update_same = fetch_data("scoresight.json", "uno_send_same", False)
        subscribe_to_data("scoresight.json", "uno_send_same", self.set_update_same)
        self.essentials = fetch_data("scoresight.json", "uno_essentials", False)
        subscribe_to_data("scoresight.json", "uno_essentials", self.set_essentials)
        self.uno_essentials_id = fetch_data("scoresight.json", "uno_essentials_id", "")
        subscribe_to_data(
            "scoresight.json", "uno_essentials_id", self.set_uno_essentials_id
        )
        self.use_overlays_format = fetch_data(
            "scoresight.json", "uno_overlays_format", False
        )
        subscribe_to_data(
            "scoresight.json", "uno_overlays_format", self.set_overlays_format
        )
        self.subCompositionId = fetch_data(
            "scoresight.json", "uno_subcomposition_id", ""
        )
        subscribe_to_data(
            "scoresight.json", "uno_subcomposition_id", self.set_subcomposition_id
        )

    def set_update_same(self, update_same):
        self.update_same = update_same

    def set_essentials(self, essentials):
        self.essentials = essentials

    def set_uno_essentials_id(self, uno_essentials_id):
        self.uno_essentials_id = uno_essentials_id

    def set_overlays_format(self, use_overlays_format):
        self.use_overlays_format = use_overlays_format

    def set_subcomposition_id(self, subCompositionId):
        self.subCompositionId = subCompositionId

    def set_log_callback(self, callback):
        """Set a callback function to receive log messages for the UI terminal."""
        self._log_callback = callback

    def _emit_log(self, message):
        """Emit a log message to the UI terminal callback if set."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        if self._log_callback:
            self._log_callback(log_line)

    @classmethod
    def _format_response_body(cls, response):
        """Format a response body for display in the log terminal.

        Detects HTML responses and shows a summary instead of raw markup.
        Truncates long responses to keep the log readable.
        """
        content_type = response.headers.get("Content-Type", "")
        text = response.text.strip()

        if "text/html" in content_type or (
            text and text[:15].lower().startswith(("<!doctype", "<html"))
        ):
            return "[HTML page returned — expected JSON. Check URL.]"

        max_len = cls.MAX_RESPONSE_LOG_LENGTH
        if len(text) > max_len:
            return text[:max_len] + "… (truncated)"
        return text

    def set_field_mapping(self, field_mapping):
        logger.debug(f"Setting UNO field mapping: {field_mapping}")
        self.field_mapping = field_mapping

    def update_uno(self, detection: list[TextDetectionTargetWithResult]):
        if not self.running:
            return

        if not self.field_mapping:
            logger.debug("Field mapping is not set")
            return

        look_in = [TextDetectionTargetWithResult.ResultState.Success]
        if self.update_same:
            look_in.append(TextDetectionTargetWithResult.ResultState.SameNoChange)

        # Check if we're using overlays format
        if self.use_overlays_format:
            # Collect all fields that need updating
            updates = {}
            for target in detection:
                if target.result_state in look_in and target.name in self.field_mapping:
                    field_name = self.field_mapping[target.name]
                    updates[field_name] = target.result

            # Send batch update if there are any updates
            if updates:
                self.send_uno_overlays_batch(updates)
        else:
            # Use existing individual update behavior
            for target in detection:
                if target.result_state in look_in and target.name in self.field_mapping:
                    uno_command = self.field_mapping[target.name]
                    self.send_uno_command(uno_command, target.result)

    def send_uno_command(self, command, value):
        if not self.essentials:
            payload = {"command": command, "value": value}
        else:
            payload = {
                "command": "SetOverlayContentField",
                "value": value,
                "fieldId": command,
                "id": self.uno_essentials_id,
            }

        endpoint = self.endpoint

        def _do_request():
            self._emit_log(f"→ PUT {endpoint}")
            self._emit_log(f"  Request body: {json.dumps(payload)}")
            try:
                response = requests.put(endpoint, json=payload)
                body = self._format_response_body(response)
                self._emit_log(f"← Response [{response.status_code}]: {body}")
                if response.status_code != 200:
                    logger.error(
                        f"Failed to send data to UNO API, status code: {response.status_code}"
                    )
                else:
                    logger.debug(f"Successfully sent {command}: {value} to UNO API")
                self.check_rate_limits(response.headers)
            except requests.exceptions.RequestException as e:
                self._emit_log(f"✗ Request failed: {e}")
                logger.error(f"Failed to send data to UNO API: {e}")

        threading.Thread(target=_do_request, daemon=True).start()

    def send_uno_overlays_batch(self, updates):
        """Send batched updates using overlays format with PATCH request."""
        if not self.subCompositionId:
            self._emit_log("✗ Error: subCompositionId is not set for overlays format")
            logger.error("subCompositionId is not set for overlays format")
            return

        payload = [
            {
                "subCompositionId": self.subCompositionId,
                "payload": updates,
            }
        ]

        endpoint = self.endpoint

        def _do_request():
            self._emit_log(f"→ PATCH {endpoint}")
            self._emit_log(f"  Request body: {json.dumps(payload)}")
            try:
                response = requests.patch(endpoint, json=payload)
                body = self._format_response_body(response)
                self._emit_log(f"← Response [{response.status_code}]: {body}")
                if response.status_code != 200:
                    logger.error(
                        f"Failed to send overlays batch to UNO API, status code: {response.status_code}"
                    )
                else:
                    logger.debug(
                        f"Successfully sent overlays batch to UNO API: {updates}"
                    )
                self.check_rate_limits(response.headers)
            except requests.exceptions.RequestException as e:
                self._emit_log(f"✗ Request failed: {e}")
                logger.error(f"Failed to send overlays batch to UNO API: {e}")

        threading.Thread(target=_do_request, daemon=True).start()

    def check_rate_limits(self, headers):
        rate_limit_headers = [
            "X-Singular-Ratelimit-Burst-Calls",
            "X-Singular-Ratelimit-Daily-Calls",
            "X-Singular-Ratelimit-Burst-Data",
            "X-Singular-Ratelimit-Daily-Data",
        ]

        for header in rate_limit_headers:
            if header in headers:
                limit_info = headers[header]
                logger.debug(f"Rate limit info for {header}: {limit_info}")

                # You can add more sophisticated rate limit handling here if needed
                # For example, pause requests if limits are close to being reached

    def test_connection(self, on_finished=None):
        """Send a test request to the UNO endpoint to verify connectivity.

        Runs the HTTP request on a background thread.
        on_finished is an optional callback invoked (from the background thread)
        when the test completes.
        """
        endpoint = self.endpoint
        use_overlays = self.use_overlays_format
        sub_id = self.subCompositionId

        def _do_test():
            self._emit_log("--- Test Connection ---")
            self._emit_log(f"Endpoint: {endpoint}")

            if use_overlays:
                if not sub_id:
                    self._emit_log(
                        "✗ Error: subCompositionId is not set for overlays format"
                    )
                    return
                payload = [{"subCompositionId": sub_id, "payload": {}}]
                self._emit_log(f"→ PATCH {endpoint}")
                self._emit_log(f"  Request body: {json.dumps(payload)}")
                try:
                    response = requests.patch(endpoint, json=payload)
                    body = self._format_response_body(response)
                    self._emit_log(f"← Response [{response.status_code}]: {body}")
                    if response.status_code == 200:
                        self._emit_log("✓ Connection successful!")
                    else:
                        self._emit_log(
                            f"✗ Connection returned status {response.status_code}"
                        )
                except requests.exceptions.RequestException as e:
                    self._emit_log(f"✗ Connection failed: {e}")
            else:
                payload = {"command": "ping", "value": ""}
                self._emit_log(f"→ PUT {endpoint}")
                self._emit_log(f"  Request body: {json.dumps(payload)}")
                try:
                    response = requests.put(endpoint, json=payload)
                    body = self._format_response_body(response)
                    self._emit_log(f"← Response [{response.status_code}]: {body}")
                    if response.status_code == 200:
                        self._emit_log("✓ Connection successful!")
                    else:
                        self._emit_log(
                            f"✗ Connection returned status {response.status_code}"
                        )
                except requests.exceptions.RequestException as e:
                    self._emit_log(f"✗ Connection failed: {e}")

            self._emit_log("--- End Test ---")
            if on_finished:
                on_finished()

        threading.Thread(target=_do_test, daemon=True).start()

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
