import io
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from aurora.__main__ import checkpoint, deliver, load_state, publish
from aurora.decision import forecast_alerts, urgent_alert
from aurora.demo import scenario
from aurora.feeds import FIELDS, HOUR, KpBin, parse_active, parse_forecast, parse_weather
from aurora.sites import SITES


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.start, self.bins, self.weather = scenario()

    def evaluate(self, lead, history=None):
        return list(forecast_alerts(self.start - lead * HOUR, self.bins, self.weather, history or {}))

    def test_stages_and_local_window(self):
        for lead, stage, status in [(60, "early", "VIGILANCIA"), (24, "action", "CONDICIONAL"),
                                    (9, "final", "CONDICIONAL"), (3, "final", "CONDICIONAL")]:
            with self.subTest(lead=lead):
                [alert] = self.evaluate(lead)
                self.assertEqual((alert.stage, alert.status, alert.night), (stage, status, "2026-11-12"))
                self.assertEqual(alert.end, self.start + 2 * HOUR)
                self.assertIn("19:00–21:00 EST", alert.body)
        self.assertEqual(self.evaluate(40), [])

    def test_missing_weather_is_unknown(self):
        self.weather.clear()
        [alert] = self.evaluate(9)
        self.assertEqual(alert.status, "DATOS INSUFICIENTES")

    def test_cloud_ice_wind_and_darkness_gates(self):
        for bad in [{"cloud": 90}, {"precip": 1}, {"gusts": 50}, {"temperature": -20},
                    {"visibility": 1000}, {"code": 66}, {"daylight": 1}]:
            with self.subTest(bad=bad):
                self.start, self.bins, self.weather = scenario()
                self.weather[SITES[0].name] = {
                    hour: replace(value, **bad) for hour, value in self.weather[SITES[0].name].items()
                }
                alerts = self.evaluate(9)
                self.assertEqual(len(alerts), 1)
                self.assertTrue(all(alert.status == "NO-GO" for alert in alerts))

    def test_partial_park_window_cannot_be_a_two_hour_candidate(self):
        self.bins = [KpBin(self.start + HOUR, 7)]
        [alert] = self.evaluate(9)
        self.assertEqual(alert.status, "NO-GO")
        self.bins = [KpBin(self.start + 2 * HOUR, 9)]
        self.assertEqual(self.evaluate(9), [])

    def test_monitoring_cutoff_uses_montreal_date(self):
        self.start = self.start.replace(month=12, day=27)
        self.bins = [KpBin(self.start, 9)]
        [alert] = self.evaluate(24)
        self.assertEqual(alert.night, "2026-12-27")
        self.start = self.start.replace(day=28)
        self.bins = [KpBin(self.start, 9)]
        self.assertEqual(self.evaluate(24), [])

    def test_downgrade_and_dedup_for_same_night(self):
        [alert] = self.evaluate(9)
        history = {alert.night: {"final": {"status": alert.status, "start": alert.start.isoformat(),
                                            "end": alert.end.isoformat()}}}
        self.assertEqual(self.evaluate(8, history), [])
        self.bins = [KpBin(self.start, 2)]
        [update] = self.evaluate(7, history)
        self.assertEqual((update.stage, update.status), ("downgrade", "NO-GO"))
        history[alert.night]["downgrade"] = {}
        self.assertEqual(self.evaluate(6, history), [])

    def test_alert_loses_weather_after_first_hour_without_false_cancellation(self):
        [alert] = self.evaluate(9)
        history = {alert.night: {"final": {"status": alert.status, "start": alert.start.isoformat(),
                                            "end": alert.end.isoformat()}}}
        self.assertEqual(self.evaluate(-0.1, history), [])

    def test_material_forecast_drop_after_preparation_gets_update(self):
        [alert] = self.evaluate(24)
        history = {alert.night: {"action": {"status": alert.status, "start": alert.start.isoformat(),
                                             "end": alert.end.isoformat()}}}
        self.bins = []
        self.assertEqual(self.evaluate(9, history), [])
        self.bins = [KpBin(self.start, 2)]
        [update] = self.evaluate(9, history)
        self.assertEqual((update.stage, update.status), ("downgrade", "NO-GO"))

    def test_urgent_requires_remaining_dark_and_clear_access_window(self):
        alert = urgent_alert(self.start, (self.start, 7.33), self.weather, {})
        self.assertEqual((alert.stage, alert.status), ("urgent", "CONDICIONAL"))
        self.assertIsNone(urgent_alert(self.start, (self.start, 7.33), {}, {}))
        self.assertIsNone(urgent_alert(self.start, (self.start, 7.33), self.weather, {alert.night: {"urgent": {}}}))
        late = self.start + 2 * HOUR
        self.assertIsNone(urgent_alert(late, (late, 8), self.weather, {}))


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.now, _, _ = scenario()

    def test_noaa_current_schema_and_legacy_table(self):
        rows = [{"time_tag": self.now.isoformat(), "kp": 6, "observed": "estimated"},
                {"time_tag": (self.now + 3 * HOUR).isoformat(), "kp": 7, "observed": "predicted"}]
        table = [list(rows[0])] + [list(row.values()) for row in rows]
        self.assertEqual(parse_forecast(rows, self.now), parse_forecast(table, self.now))
        with self.assertRaises(ValueError):
            parse_forecast(rows, self.now + 14 * HOUR)

    def test_minute_estimate_fresh_sustained_and_order_independent(self):
        rows = [{"time_tag": (self.now - timedelta(minutes=minutes)).isoformat(), "estimated_kp": 7.33}
                for minutes in range(6)]
        self.assertEqual(parse_active(rows[::-1], self.now), (self.now, 7.33))
        self.assertIsNone(parse_active([rows[0]] * 6, self.now))
        self.assertIsNone(parse_active(rows[:2] + rows[5:], self.now))
        with self.assertRaises(ValueError):
            parse_active(rows, self.now + timedelta(minutes=11))

    def test_hourly_weather_requires_aligned_utc_samples_and_skips_null(self):
        payload = {"utc_offset_seconds": 0, "hourly": {
            "time": ["2026-11-12T18:00", "2026-11-12T19:00"],
            **{key: [value, None] for key, value in zip(FIELDS, (10, 5, 20_000, 0, -5, 10, 1, 0), strict=True)},
        }}
        [weather] = parse_weather(payload).values()
        self.assertTrue(weather.suitable)
        payload["hourly"]["cloud_cover"].pop()
        with self.assertRaises(ValueError):
            parse_weather(payload)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        start, bins, weather = scenario()
        [self.alert] = forecast_alerts(start - 9 * HOUR, bins, weather, {})

    def test_history_committed_before_send_and_reloaded_for_dedup(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "history" / "events.json"
            history = load_state(path)

            def save(message):
                checkpoint(path, history, False, message)

            def confirm(*args):
                self.assertEqual(load_state(path)[self.alert.night]["final"]["delivery"], "pending")
                return "abc"

            with patch("aurora.__main__.publish", side_effect=confirm) as push:
                deliver(self.alert, "topic", history, save)
                deliver(self.alert, "topic", load_state(path), save)
                self.assertEqual(push.call_count, 1)
            record = load_state(path)[self.alert.night]["final"]
            self.assertEqual((record["delivery"], record["message_id"]), ("accepted", "abc"))
            self.assertNotIn("topic", path.read_text(encoding="utf-8"))

    @patch("aurora.__main__.publish")
    def test_cannot_publish_when_reservation_fails(self, push):
        with self.assertRaises(OSError):
            deliver(self.alert, "topic", {}, Mock(side_effect=OSError))
        push.assert_not_called()

    @patch("aurora.__main__.publish", side_effect=RuntimeError)
    def test_ambiguous_network_failure_is_not_republished(self, push):
        history = {}
        save = Mock()
        with self.assertRaises(RuntimeError):
            deliver(self.alert, "topic", history, save)
        self.assertEqual(history[self.alert.night]["final"]["delivery"], "unconfirmed")
        deliver(self.alert, "topic", history, save)
        push.assert_called_once()

    @patch("aurora.__main__.urlopen")
    def test_ntfy_payload_and_receipt(self, urlopen):
        urlopen.return_value = io.BytesIO(b'{"event":"message","id":"abc"}')
        self.assertEqual(publish("topic", "Prueba", "Observación"), "abc")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://ntfy.sh")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data)["message"], "Observación")


if __name__ == "__main__":
    unittest.main()
