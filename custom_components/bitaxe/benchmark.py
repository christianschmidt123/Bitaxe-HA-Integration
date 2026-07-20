import os
import time
import json
import logging
import requests
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Konfiguration und Sicherheitsgrenzen
BENCHMARK_TIME = 600      # 10 Minuten pro Schritt
SAMPLE_INTERVAL = 10     # Alle 10 Sekunden messen
SLEEP_TIME = 90          # Wartezeit nach einer Einstellungsänderung für Stabilität

MAX_TEMP = 66            # Maximal erlaubte ASIC-Temperatur
MAX_VR_TEMP = 86         # Maximal erlaubte VR-Temperatur
MIN_INPUT_VOLTAGE_RATIO = 11.0 / 12.0  # Minimale Netzteilspannung relativ zur Nominalspannung
MAX_INPUT_VOLTAGE_RATIO = 12.6 / 12.0  # Maximale Netzteilspannung relativ zur Nominalspannung

MAX_ALLOWED_VOLTAGE = 1400   # Absolutes Maximum Chip-Spannung (mV)
MAX_ALLOWED_FREQUENCY = 1200 # Absolutes Maximum Frequenz (MHz)
FREQUENCY_STEP = 25
VOLTAGE_STEP = 20
MAX_AVG_ERROR_PERCENT = 2.0  # Mittlere ASIC-Fehlerquote pro 10 Minuten

OC_UNLOCK_PATH = "/#/settings?oc="
SETTINGS_KEY_MAP = {
    "display": "display",
    "rotation": "rotation",
    "invertscreen": "invertscreen",
    "displayTimeout": "displayTimeout",
    "autofanspeed": "autofanspeed",
    "manualFanSpeed": "manualFanSpeed",
    "minFanSpeed": "minfanspeed",
    "temptarget": "temptarget",
    "overheat_mode": "overheat_mode",
    "statsFrequency": "statsFrequency",
}

def get_status_path(hass: HomeAssistant, entry_id: str) -> str:
    """Gibt den Pfad zur Status-Datei zurück."""
    return hass.config.path(".storage", f"bitaxe_bench_{entry_id}.json")

def get_cancel_path(hass: HomeAssistant, entry_id: str) -> str:
    """Gibt den Pfad zur Abbruch-Datei zurück."""
    return hass.config.path(".storage", f"bitaxe_bench_{entry_id}.cancel")

def load_benchmark_status(hass: HomeAssistant, entry_id: str):
    path = get_status_path(hass, entry_id)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def save_benchmark_status(hass: HomeAssistant, entry_id: str, state):
    path = get_status_path(hass, entry_id)
    try:
        with open(path, "w") as f:
            json.dump(state, f)
    except Exception as e:
        _LOGGER.error(f"Fehler beim Speichern des Benchmark-Status: {e}")


def clear_benchmark_status(hass: HomeAssistant, entry_id: str):
    path = get_status_path(hass, entry_id)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        _LOGGER.warning(f"Fehler beim Löschen des Benchmark-Status: {e}")


def clear_benchmark_cancel(hass: HomeAssistant, entry_id: str):
    cancel_path = get_cancel_path(hass, entry_id)
    try:
        if os.path.exists(cancel_path):
            os.remove(cancel_path)
    except Exception as e:
        _LOGGER.warning(f"Fehler beim Löschen des Abbruch-Signals: {e}")


def fetch_system_info(bitaxe_ip):
    res = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
    res.raise_for_status()
    return res.json()


def unlock_overclock(bitaxe_ip):
    try:
        res = requests.get(f"{bitaxe_ip}{OC_UNLOCK_PATH}", timeout=10)
        res.raise_for_status()
    except Exception as e:
        _LOGGER.warning(f"Fehler beim Freischalten von Overclocking: {e}")


def build_settings_payload(info, voltage, frequency):
    payload = {}

    for read_key, write_key in SETTINGS_KEY_MAP.items():
        if read_key in info:
            payload[write_key] = info[read_key]

    payload["coreVoltage"] = voltage
    payload["frequency"] = frequency
    return payload


def cancel_benchmark(hass: HomeAssistant, entry_id: str):
    """Erstellt das Abbruch-Signal für den Hintergrund-Thread."""
    cancel_path = get_cancel_path(hass, entry_id)
    try:
        with open(cancel_path, "w") as f:
            f.write("cancel")
    except Exception as e:
        _LOGGER.error(f"Fehler beim Erstellen des Abbruch-Signals: {e}")

def check_and_clear_cancel(hass: HomeAssistant, entry_id: str) -> bool:
    """Prüft, ob abgebrochen werden soll und löscht das Signal danach."""
    cancel_path = get_cancel_path(hass, entry_id)
    if os.path.exists(cancel_path):
        try:
            os.remove(cancel_path)
        except Exception:
            pass
        return True
    return False

def fire_update(hass: HomeAssistant, entry_id: str, status: str, progress: float = 0, best_mhz=None, best_mv=None):
    """Sendet Echtzeitdaten an die Live-Sensoren."""
    hass.bus.fire(f"bitaxe_bench_update_{entry_id}", {
        "status": status,
        "progress": round(progress, 1),
        "best_mhz": best_mhz,
        "best_mv": best_mv
    })

def fetch_device_specs(bitaxe_ip):
    info = fetch_system_info(bitaxe_ip)
    return (
        int(info.get("smallCoreCount", 0)),
        int(info.get("asicCount", 1)),
        int(info.get("coreVoltage", 1150)),
        int(info.get("frequency", 525))
    )

def set_system_settings(bitaxe_ip, voltage, frequency):
    try:
        info = fetch_system_info(bitaxe_ip)
        payload = build_settings_payload(info, voltage, frequency)
        res = requests.patch(f"{bitaxe_ip}/api/system", json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        _LOGGER.warning(f"Fehler beim Senden der Config an BitAxe: {e}")


STOP_REASON_LABELS = {
    "THERMAL_LIMIT": "{metric}-Temperaturlimit erreicht (gemessen: {value:.1f}°C, Grenze: {limit}°C)",
    "POWER_LIMIT": "Leistungslimit erreicht (gemessen: {value:.1f}W, Grenze: {limit}W)",
    "INPUT_VOLTAGE_FAULT": "Eingangsspannung außerhalb des zulässigen Bereichs (gemessen: {value:.2f}V, zulässig: {min:.2f}V\u2013{max:.2f}V)",
    "UNSTABLE_CONNECTION": "Verbindung zum Bitaxe instabil (nur {received}/{required} gültige Messwerte erhalten)",
    "ZERO_HASHRATE": "Keine Hashrate gemessen (Ø {value:.2f} GH/s)",
    "USER_CANCELLED": "Manuell abgebrochen",
    "MAX_VOLTAGE_REACHED": "Maximale Spannung erreicht, Fehlerquote weiterhin zu hoch (gemessen: {error:.2f}%, Grenze: {limit:.2f}%, bei {voltage}mV)",
    "SEARCH_EXHAUSTED": "Suche beendet, Grenzwerte erreicht (Spannung: {voltage}mV, Frequenz: {frequency}MHz)",
}


def finalize_benchmark(hass, entry_id, bitaxe_ip, state, default_voltage, default_frequency, is_cancelled, stop_reason=None, stop_details=None):
    best_voltage = state.get("best_mv") if state else None
    best_frequency = state.get("best_mhz") if state else None
    raw_label = STOP_REASON_LABELS.get(stop_reason)
    if raw_label:
        try:
            reason_text = raw_label.format(**(stop_details or {}))
        except (KeyError, ValueError, TypeError):
            reason_text = raw_label
    else:
        reason_text = None
    reason_suffix = f" - Grund: {reason_text}" if reason_text else ""

    if best_voltage is not None and best_frequency is not None:
        set_system_settings(bitaxe_ip, best_voltage, best_frequency)
        final_msg = f"Abgebrochen (Bestwert gesetzt!){reason_suffix}" if is_cancelled else f"Beendet (Bestwert gesetzt!){reason_suffix}"
    else:
        set_system_settings(bitaxe_ip, default_voltage, default_frequency)
        final_msg = f"Abgebrochen (Standardwerte wiederhergestellt){reason_suffix}" if is_cancelled else f"Beendet (Standardwerte wiederhergestellt){reason_suffix}"

    clear_benchmark_status(hass, entry_id)
    clear_benchmark_cancel(hass, entry_id)
    fire_update(hass, entry_id, final_msg, 100, best_frequency, best_voltage)

def run_benchmark_step(hass, entry_id, bitaxe_ip, max_power, min_input_voltage, max_input_voltage):
    """Führt eine einzelne Stufe aus und prüft regelmäßig auf Abbruch."""
    hash_rates, temperatures, power_consumptions, vr_temps, error_rates = [], [], [], [], []
    total_samples = BENCHMARK_TIME // SAMPLE_INTERVAL

    for sample in range(total_samples):
        # Abbruch mitten im Schritt prüfen
        if check_and_clear_cancel(hass, entry_id):
            return None, "USER_CANCELLED", {}

        try:
            res = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
            if res.status_code == 200:
                info = res.json()
                temp = info.get("temp")
                vr_temp = info.get("vrTemp")
                voltage = info.get("voltage")
                voltage_v = voltage / 1000.0 if voltage else None
                hash_rate = info.get("hashRate")
                power = info.get("power")
                error_percentage = info.get("errorPercentage")
                
                if temp is not None and hash_rate is not None and power is not None:
                    if temp >= MAX_TEMP:
                        return None, "THERMAL_LIMIT", {"metric": "ASIC", "value": temp, "limit": MAX_TEMP}
                    if vr_temp and vr_temp >= MAX_VR_TEMP:
                        return None, "THERMAL_LIMIT", {"metric": "VR", "value": vr_temp, "limit": MAX_VR_TEMP}
                    if voltage_v and (voltage_v < min_input_voltage or voltage_v > max_input_voltage):
                        return None, "INPUT_VOLTAGE_FAULT", {"value": voltage_v, "min": min_input_voltage, "max": max_input_voltage}
                    if power > max_power:
                        return None, "POWER_LIMIT", {"value": power, "limit": max_power}

                    hash_rates.append(hash_rate)
                    temperatures.append(temp)
                    power_consumptions.append(power)
                    if vr_temp:
                        vr_temps.append(vr_temp)
                    if error_percentage is not None:
                        error_rates.append(error_percentage)

                    samples_done = sample + 1
                    avg_error = sum(error_rates) / len(error_rates) if error_rates else None
                    progress = (samples_done / total_samples) * 100
                    status = f"Messe {samples_done}/{total_samples}"
                    if avg_error is not None:
                        status = f"{status} (Fehler Ø {avg_error:.2f}%)"
                    fire_update(hass, entry_id, status, progress)
        except Exception:
            pass
        time.sleep(SAMPLE_INTERVAL)

    if len(hash_rates) < (total_samples * 0.7):
        return None, "UNSTABLE_CONNECTION", {"received": len(hash_rates), "required": total_samples}

    avg_hash = sum(hash_rates) / len(hash_rates)
    avg_power = sum(power_consumptions) / len(power_consumptions)
    avg_error = sum(error_rates) / len(error_rates) if error_rates else None
    
    if avg_hash < 1.0: 
        return None, "ZERO_HASHRATE", {"value": avg_hash}

    return {"avg_hash": avg_hash, "avg_power": avg_power, "avg_error": avg_error, "efficiency": avg_power / avg_hash}, None, {}

def run_bitaxe_benchmark(hass: HomeAssistant, entry_id: str, ip_address: str, max_power: int = 40, initial_voltage: int = 1150, initial_frequency: int = 525):
    bitaxe_ip = f"http://{ip_address}"
    
    # Sicherstellen, dass ein eventuelles altes Abbruchsignal gelöscht ist
    check_and_clear_cancel(hass, entry_id)
    
    try:
        small_core_count, asic_count, def_v, def_f = fetch_device_specs(bitaxe_ip)
    except Exception:
        fire_update(hass, entry_id, "Fehler: Verbindung fehlgeschlagen")
        return

    try:
        info = fetch_system_info(bitaxe_ip)
    except Exception:
        fire_update(hass, entry_id, "Fehler: Verbindung fehlgeschlagen")
        return

    if not int(info.get("overclockEnabled", 0)):
        unlock_overclock(bitaxe_ip)
        try:
            info = fetch_system_info(bitaxe_ip)
        except Exception:
            fire_update(hass, entry_id, "Fehler: Verbindung fehlgeschlagen")
            return

        if not int(info.get("overclockEnabled", 0)):
            _LOGGER.error("Overclocking konnte nicht freigeschaltet werden.")
            fire_update(hass, entry_id, "Fehler: Overclocking konnte nicht freigeschaltet werden")
            return

    nominal_voltage = float(info.get("nominalVoltage") or 12)
    min_input_voltage = nominal_voltage * MIN_INPUT_VOLTAGE_RATIO
    max_input_voltage = nominal_voltage * MAX_INPUT_VOLTAGE_RATIO

    state = load_benchmark_status(hass, entry_id)
    if not state or not state.get("is_running"):
        state = {
            "current_voltage": initial_voltage,
            "current_frequency": initial_frequency,
            "results": [],
            "best_mhz": None,
            "best_mv": None,
            "is_running": True,
            "max_power": max_power
        }
        save_benchmark_status(hass, entry_id, state)
    else:
        max_power = state.get("max_power", max_power)
        state["is_running"] = True
        save_benchmark_status(hass, entry_id, state)

    fire_update(hass, entry_id, "Läuft (Bereite vor...)", 0, state["best_mhz"], state["best_mv"])
    
    stop_reason = None
    stop_details = {}

    while state["current_voltage"] <= MAX_ALLOWED_VOLTAGE and state["current_frequency"] <= MAX_ALLOWED_FREQUENCY:
        # Vor Schleifenbeginn auf Abbruch prüfen
        if check_and_clear_cancel(hass, entry_id):
            stop_reason = "USER_CANCELLED"
            break

        progress = ((state["current_voltage"] - initial_voltage) / (MAX_ALLOWED_VOLTAGE - initial_voltage + 1)) * 100
        avg_error_text = ""
        if state.get("last_avg_error") is not None:
            avg_error_text = f", Fehler Ø {state['last_avg_error']:.2f}%"
        fire_update(
            hass, entry_id, 
            f"Teste {state['current_frequency']}MHz @ {state['current_voltage']}mV ({max_power}W Limit{avg_error_text})", 
            progress, state["best_mhz"], state["best_mv"]
        )
        
        set_system_settings(bitaxe_ip, state["current_voltage"], state["current_frequency"])
        time.sleep(SLEEP_TIME)
        
        res, err, err_details = run_benchmark_step(hass, entry_id, bitaxe_ip, max_power, min_input_voltage, max_input_voltage)
        
        if err == "USER_CANCELLED":
            stop_reason = "USER_CANCELLED"
            break

        if err in {"THERMAL_LIMIT", "POWER_LIMIT", "INPUT_VOLTAGE_FAULT"}:
            _LOGGER.info(f"Benchmark endet wegen hartem Limit: {err}")
            stop_reason = err
            stop_details = err_details
            break
            
        if err:
            _LOGGER.info(f"Stufe fehlgeschlagen wegen: {err}. Passe Suchpfad an...")
            if state["current_voltage"] < MAX_ALLOWED_VOLTAGE:
                state["current_voltage"] = min(MAX_ALLOWED_VOLTAGE, state["current_voltage"] + VOLTAGE_STEP)
            elif state["current_frequency"] > initial_frequency:
                state["current_frequency"] = max(initial_frequency, state["current_frequency"] - FREQUENCY_STEP)
            else:
                stop_reason = err
                stop_details = err_details
                break
            save_benchmark_status(hass, entry_id, state)
            continue

        state["last_avg_error"] = res["avg_error"]

        if res["avg_error"] is not None and res["avg_error"] > MAX_AVG_ERROR_PERCENT:
            _LOGGER.info(
                f"Durchschnittliche Fehlerquote {res['avg_error']:.2f}% zu hoch, erhöhe Spannung bei {state['current_frequency']}MHz"
            )
            if state["current_voltage"] < MAX_ALLOWED_VOLTAGE:
                state["current_voltage"] = min(MAX_ALLOWED_VOLTAGE, state["current_voltage"] + VOLTAGE_STEP)
                save_benchmark_status(hass, entry_id, state)
                continue

            _LOGGER.info("Maximale Spannung erreicht, Benchmark wird beendet.")
            stop_reason = "MAX_VOLTAGE_REACHED"
            stop_details = {"error": res["avg_error"], "limit": MAX_AVG_ERROR_PERCENT, "voltage": state["current_voltage"]}
            break

        # Erfolg auswerten
        state["results"].append({
            "freq": state["current_frequency"],
            "volt": state["current_voltage"],
            "hash": res["avg_hash"],
            "error": res["avg_error"],
            "efficiency": res["efficiency"]
        })
        
        state["best_mhz"] = state["current_frequency"]
        state["best_mv"] = state["current_voltage"]
        
        # Frequenz erhöhen
        state["current_frequency"] += FREQUENCY_STEP
        save_benchmark_status(hass, entry_id, state)

    # Beendigung verarbeiten (Entweder durch Abbruch oder fertig)
    is_cancelled = not (state["current_voltage"] <= MAX_ALLOWED_VOLTAGE and state["current_frequency"] <= MAX_ALLOWED_FREQUENCY)
    if stop_reason is None and is_cancelled:
        stop_reason = "SEARCH_EXHAUSTED"
        stop_details = {"voltage": state["current_voltage"], "frequency": state["current_frequency"]}
    finalize_benchmark(hass, entry_id, bitaxe_ip, state, def_v, def_f, is_cancelled, stop_reason, stop_details)
