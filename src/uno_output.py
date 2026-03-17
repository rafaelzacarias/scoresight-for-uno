import json
import re
import time
import threading
from datetime import datetime

import requests
from text_detection_target import TextDetectionTargetWithResult
from sc_logging import logger
from storage import subscribe_to_data, fetch_data


class UNOAPI:
    MAX_RESPONSE_LOG_LENGTH = 500

    # Field names that should be routed to the "clock" sub-composition.
    # Everything else goes to the "scores" sub-composition.
    CLOCK_FIELDS = {"ocrClock", "SetMatchTime", "Clock", "Game Clock Control"}

    # Patterns to extract the control-app token from any known URL format
    _TOKEN_PATTERNS = [
        # https://app.overlays.uno/control/<token>  (user-facing URL)
        re.compile(r'https?://app\.overlays\.uno/control/([^/]+?)(?:/api)?/?$'),
        # https://app.overlays.uno/apiv2/controlapps/<token>/...
        re.compile(r'https?://app\.overlays\.uno/apiv2/controlapps/([^/]+)'),
        # https://app.singular.live/apiv2/controlapps/<token>/...
        re.compile(r'https?://app\.singular\.live/apiv2/controlapps/([^/]+)'),
    ]

    _API_BASE = 'https://app.singular.live/apiv2/controlapps'

    @classmethod
    def normalize_endpoint(cls, url: str) -> str:
        """Extract the control-app token from any known URL format and
        return the canonical ``singular.live`` PATCH ``/control`` endpoint."""
        url = url.strip()
        for pattern in cls._TOKEN_PATTERNS:
            m = pattern.search(url)
            if m:
                token = m.group(1)
                result = f'{cls._API_BASE}/{token}/control'
                if result != url:
                    logger.info(f"UNO endpoint resolved: {url} -> {result}")
                return result
        # If nothing matched, return as-is (user may have a fully custom URL)
        return url

    def __init__(self, endpoint, field_mapping):
        self.endpoint = self.normalize_endpoint(endpoint)
        self.field_mapping = field_mapping
        self.running = False
        self._log_callback = None
        self._rate_limit_callback = None
        # Separate rate limits for scores and clock
        self._scores_interval = 5.0  # seconds between score updates
        self._clock_interval = 1.0   # seconds between clock updates
        # Pending payloads (latest wins)
        self._scores_pending = None
        self._scores_lock = threading.Lock()
        self._scores_event = threading.Event()
        self._clock_pending = None
        self._clock_lock = threading.Lock()
        self._clock_event = threading.Event()
        # Worker threads (created once on first start())
        self._workers_started = False
        self.subCompositionIdScores = fetch_data(
            "scoresight.json", "uno_subcomposition_id_scores", ""
        )
        subscribe_to_data(
            "scoresight.json", "uno_subcomposition_id_scores",
            self.set_subcomposition_id_scores,
        )
        self.subCompositionIdClock = fetch_data(
            "scoresight.json", "uno_subcomposition_id_clock", ""
        )
        subscribe_to_data(
            "scoresight.json", "uno_subcomposition_id_clock",
            self.set_subcomposition_id_clock,
        )

    def set_subcomposition_id_scores(self, val):
        self.subCompositionIdScores = val

    def set_subcomposition_id_clock(self, val):
        self.subCompositionIdClock = val

    def _subcomp_for_field(self, field_name: str) -> str:
        """Return the appropriate subCompositionId for *field_name*."""
        if field_name in self.CLOCK_FIELDS:
            return self.subCompositionIdClock
        return self.subCompositionIdScores

    def set_log_callback(self, callback):
        """Set a callback function to receive log messages for the UI terminal."""
        self._log_callback = callback

    def set_rate_limit_callback(self, callback):
        """Set a callback to receive formatted rate-limit strings for the UI."""
        self._rate_limit_callback = callback

    def set_scores_interval(self, seconds: float):
        """Set the minimum seconds between score PATCH requests."""
        self._scores_interval = max(0.1, float(seconds))
        logger.debug(f"Scores rate limit: 1 every {self._scores_interval:.1f}s")

    def set_clock_interval(self, seconds: float):
        """Set the minimum seconds between clock PATCH requests."""
        self._clock_interval = max(0.1, float(seconds))
        logger.debug(f"Clock rate limit: 1 every {self._clock_interval:.1f}s")

    def _do_patch(self, payload):
        """Actually send a PATCH request. Called from worker threads."""
        endpoint = self.endpoint
        self._emit_log(f"→ PATCH {endpoint}")
        self._emit_log(f"  Request body: {json.dumps(payload)}")
        try:
            response = requests.patch(
                endpoint, json=payload,
                headers={"Content-Type": "application/json"},
            )
            body = self._format_response_body(response)
            self._emit_log(f"← Response [{response.status_code}]: {body}")
            if response.status_code != 200:
                logger.error(
                    f"Failed to send data to UNO API, status code: {response.status_code}"
                )
            self.check_rate_limits(response.headers)
        except requests.exceptions.RequestException as e:
            self._emit_log(f"✗ Request failed: {e}")
            logger.error(f"Failed to send data to UNO API: {e}")

    def _worker_loop(self, lock, event, pending_attr, interval_attr):
        """Persistent worker thread loop. Waits for event, sends latest payload,
        sleeps for the rate-limit interval, repeats."""
        while True:
            # Wait until signaled (or timeout to check for stop)
            event.wait(timeout=1.0)
            event.clear()

            if not self.running:
                continue  # stay alive but idle when paused

            # Grab the latest pending payload
            with lock:
                payload = getattr(self, pending_attr)
                setattr(self, pending_attr, None)

            if payload is None:
                continue

            self._do_patch(payload)

            # Sleep for the rate-limit interval
            interval = getattr(self, interval_attr)
            time.sleep(interval)

            # After sleeping, check if newer data arrived during the sleep
            # and send that too (loop will re-check)
            with lock:
                if getattr(self, pending_attr) is not None:
                    event.set()

    def _ensure_workers(self):
        """Start the two persistent worker threads if not already running."""
        if self._workers_started:
            return
        self._workers_started = True
        threading.Thread(
            target=self._worker_loop,
            args=(self._scores_lock, self._scores_event,
                  '_scores_pending', '_scores_interval'),
            daemon=True,
            name="uno-scores-worker",
        ).start()
        threading.Thread(
            target=self._worker_loop,
            args=(self._clock_lock, self._clock_event,
                  '_clock_pending', '_clock_interval'),
            daemon=True,
            name="uno-clock-worker",
        ).start()
        logger.debug("UNO worker threads started")

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

        look_in = [TextDetectionTargetWithResult.ResultState.Success,
                   TextDetectionTargetWithResult.ResultState.SameNoChange]

        # Collect all fields that need updating
        updates = {}
        for target in detection:
            if target.result_state in look_in and target.name in self.field_mapping:
                field_name = self.field_mapping[target.name]
                updates[field_name] = target.result

        # Send a single batched PATCH if there are updates
        if updates:
            self._send_batch(updates)

    def _send_batch(self, updates):
        """Group fields by sub-composition and send separate throttled PATCH
        requests for scores and clock."""
        clock_fields = {}
        score_fields = {}
        for field, value in updates.items():
            if field in self.CLOCK_FIELDS:
                sc_id = self.subCompositionIdClock
                if sc_id:
                    clock_fields[field] = value
                else:
                    self._emit_log(f"✗ Skipping '{field}': no clock sub-composition.")
            else:
                sc_id = self.subCompositionIdScores
                if sc_id:
                    score_fields[field] = value
                else:
                    self._emit_log(f"✗ Skipping '{field}': no scores sub-composition.")

        endpoint = self.endpoint

        if score_fields:
            payload = [{"subCompositionId": self.subCompositionIdScores, "payload": score_fields}]
            with self._scores_lock:
                self._scores_pending = payload
            self._scores_event.set()

        if clock_fields:
            payload = [{"subCompositionId": self.subCompositionIdClock, "payload": clock_fields}]
            with self._clock_lock:
                self._clock_pending = payload
            self._clock_event.set()

    def check_rate_limits(self, headers):
        parts = []
        for header_name, label in [
            ("X-Singular-Ratelimit-Burst-Calls", "Burst"),
            ("X-Singular-Ratelimit-Daily-Calls", "Daily"),
        ]:
            raw = headers.get(header_name)
            if not raw:
                continue
            try:
                info = json.loads(raw)
                remaining = info.get("remaining", "?")
                reset_ts = info.get("reset", 0)
                if reset_ts:
                    secs_left = max(0, int(reset_ts - time.time()))
                    if secs_left >= 3600:
                        hrs, rem = divmod(secs_left, 3600)
                        mins, secs = divmod(rem, 60)
                        reset_str = f"{hrs}h {mins}m"
                    else:
                        mins, secs = divmod(secs_left, 60)
                        reset_str = f"{mins}m {secs}s"
                else:
                    reset_str = "?"
                parts.append(f"{label}: {remaining} left, reset {reset_str}")
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.debug(f"Could not parse {header_name}: {e}")

        if parts:
            text = "  |  ".join(parts)
            logger.debug(f"Rate limits: {text}")
            if self._rate_limit_callback:
                self._rate_limit_callback(text)

    def test_connection(self, on_finished=None, on_subcompositions=None):
        """Send a test request to the UNO endpoint to verify connectivity.

        Runs the HTTP request on a background thread.
        on_finished is an optional callback invoked (from the background thread)
        when the test completes.
        on_subcompositions is an optional callback invoked with a list of
        {"subCompositionId": ..., "subCompositionName": ...} dicts parsed from
        the GET response.
        """
        endpoint = self.endpoint

        def _do_test():
            self._emit_log("--- Test Connection ---")
            self._emit_log(f"Endpoint: {endpoint}")
            self._emit_log(f"→ GET {endpoint}")
            subcompositions = []
            try:
                response = requests.get(endpoint)
                body = self._format_response_body(response)
                self._emit_log(f"← Response [{response.status_code}]: {body}")
                if response.status_code == 200:
                    self._emit_log("✓ Connection successful!")
                    # Parse subcompositions from response
                    try:
                        data = response.json()
                        if isinstance(data, list):
                            for item in data:
                                sc_id = item.get("subCompositionId", "")
                                sc_name = item.get("subCompositionName", "")
                                payload_fields = []
                                if isinstance(item.get("payload"), dict):
                                    payload_fields = list(item["payload"].keys())
                                if sc_id and sc_name:
                                    subcompositions.append({
                                        "subCompositionId": sc_id,
                                        "subCompositionName": sc_name,
                                        "fields": payload_fields,
                                    })
                            self._emit_log(
                                f"Found {len(subcompositions)} sub-composition(s): "
                                + ", ".join(s['subCompositionName'] for s in subcompositions)
                            )
                    except (ValueError, KeyError) as e:
                        self._emit_log(f"⚠ Could not parse sub-compositions: {e}")
                else:
                    self._emit_log(
                        f"✗ Connection returned status {response.status_code}"
                    )
            except requests.exceptions.RequestException as e:
                self._emit_log(f"✗ Connection failed: {e}")

            self._emit_log("--- End Test ---")
            if on_subcompositions and subcompositions:
                on_subcompositions(subcompositions)
            if on_finished:
                on_finished()

        threading.Thread(target=_do_test, daemon=True).start()

    def start(self):
        self.running = True
        self._ensure_workers()

    def stop(self):
        self.running = False
