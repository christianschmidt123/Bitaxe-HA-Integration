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
SLEEP_TIME = 90          # Wartezeit nach Neustart für Stabilität

MAX_TEMP = 66            # Maximal erlaubte ASIC-Temperatur
MAX_VR_TEMP = 86         # Maximal erlaubte VR-Temperatur
MIN_INPUT_VOLTAGE = 11.0 # Minimale Netzteilspannung unter Last
MAX_INPUT_VOLTAGE = 12.6 # Maximale Netzteilspannung

MAX_ALLOWED_VOLTAGE = 1400   # Absolutes Maximum Chip-Spannung (mV)
MAX_ALLOWED_FREQUENCY = 1200 # Absolutes Maximum Frequenz (MHz)

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
    res = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
    info = res.json()
    return (
        int(info.get("smallCoreCount", 0)),
        int(info.get("asicCount", 1)),
        int(info.get("coreVoltage", 1150)),
        int(info.get("frequency", 500))
    )

def set_system_settings(bitaxe_ip, voltage, frequency):
    try:
        # Erst Einstellungen setzen
        requests.post(f"{bitaxe_ip}/api/system/settings", json={
            "coreVoltage": voltage,
            "frequency": frequency
        }, timeout=10)
        time.sleep(2)
        # Danach Gerät neu starten, damit die Frequenz greift
        requests.post(f"{bitaxe_ip}/api/system/restart", timeout=5)
    except Exception as e:
        _LOGGER.warning(f"Fehler beim Senden der Config an BitAxe: {e}")

def run_benchmark_step(hass, entry_id, bitaxe_ip, max_power):
    """Führt eine einzelne Stufe aus und prüft regelmäßig auf Abbruch."""
    hash_rates, temperatures, power_consumptions, vr_temps = [], [], [], []
    total_samples = BENCHMARK_TIME // SAMPLE_INTERVAL

    for sample in range(total_samples):
        # Abbruch mitten im Schritt prüfen
        if check_and_clear_cancel(hass, entry_id):
            return None, "USER_CANCELLED"

        try:
            res = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
            if res.status_code == 200:
                info = res.json()
                temp = info.get("temp")
                vr_temp = info.get("vrTemp")
                voltage = info.get("voltage")
                hash_rate = info.get("hashRate")
                power = info.get("power")
                
                if temp is not None and hash_rate is not None and power is not None:
                    if temp >= MAX_TEMP or (vr_temp and vr_temp >= MAX_VR_TEMP):
                        return None, "THERMAL_LIMIT"
                    if voltage and (voltage < MIN_INPUT_VOLTAGE or voltage > MAX_INPUT_VOLTAGE):
                        return None, "INPUT_VOLTAGE_FAULT"
                    if power > max_power:
                        return None, "POWER_LIMIT"

                    hash_rates.append(hash_rate)
                    temperatures.append(temp)
                    power_consumptions.append(power)
                    if vr_temp:
                        vr_temps.append(vr_temp)
        except Exception:
            pass
        time.sleep(SAMPLE_INTERVAL)

    if len(hash_rates) < (total_samples * 0.7):
        return None, "UNSTABLE_CONNECTION"

    avg_hash = sum(hash_rates) / len(hash_rates)
    avg_power = sum(power_consumptions) / len(power_consumptions)
    
    if avg_hash < 1.0: 
        return None, "ZERO_HASHRATE"

    return {"avg_hash": avg_hash, "avg_power": avg_power, "efficiency": avg_power / avg_hash}, None

def run_bitaxe_benchmark(hass: HomeAssistant, entry_id: str, ip_address: str, max_power: int = 40, initial_voltage: int = 1150, initial_frequency: int = 500):
    bitaxe_ip = f"http://{ip_address}"
    
    # Sicherstellen, dass ein eventuelles altes Abbruchsignal gelöscht ist
    check_and_clear_cancel(hass, entry_id)
    
    try:
        small_core_count, asic_count, def_v, def_f = fetch_device_specs(bitaxe_ip)
    except Exception:
        fire_update(hass, entry_id, "Fehler: Verbindung fehlgeschlagen")
        return

    state = load_benchmark_status(hass, entry_id)
    if not state:
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
    
    while state["current_voltage"] <= MAX_ALLOWED_VOLTAGE and state["current_frequency"] <= MAX_ALLOWED_FREQUENCY:
        # Vor Schleifenbeginn auf Abbruch prüfen
        if check_and_clear_cancel(hass, entry_id):
            break

        progress = ((state["current_voltage"] - initial_voltage) / (MAX_ALLOWED_VOLTAGE - initial_voltage + 1)) * 100
        fire_update(
            hass, entry_id, 
            f"Teste {state['current_frequency']}MHz @ {state['current_voltage']}mV ({max_power}W Limit)", 
            progress, state["best_mhz"], state["best_mv"]
        )
        
        set_system_settings(bitaxe_ip, state["current_voltage"], state["current_frequency"])
        time.sleep(SLEEP_TIME)
        
        res, err = run_benchmark_step(hass, entry_id, bitaxe_ip, max_power)
        
        if err == "USER_CANCELLED":
            break
            
        if err:
            _LOGGER.info(f"Stufe fehlgeschlagen wegen: {err}. Passe Suchpfad an...")
            if state["current_frequency"] > initial_frequency:
                state["current_frequency"] -= 25
                state["current_voltage"] += 20
            else:
                state["current_voltage"] += 20
            save_benchmark_status(hass, entry_id, state)
            continue

        # Erfolg auswerten
        state["results"].append({
            "freq": state["current_frequency"],
            "volt": state["current_voltage"],
            "hash": res["avg_hash"],
            "efficiency": res["efficiency"]
        })
        
        state["best_mhz"] = state["current_frequency"]
        state["best_mv"] = state["current_voltage"]
        
        # Frequenz erhöhen
        state["current_frequency"] += 25
        save_benchmark_status(hass, entry_id, state)

    # Beendigung verarbeiten (Entweder durch Abbruch oder fertig)
    is_cancelled = not (state["current_voltage"] <= MAX_ALLOWED_VOLTAGE and state["current_frequency"] <= MAX_ALLOWED_FREQUENCY)
    
    state["is_running"] = False
    save_benchmark_status(hass, entry_id, state)
    
    if state["best_mhz"] and state["best_mv"]:
        set_system_settings(bitaxe_ip, state["best_mv"], state["best_mhz"])
        final_msg = f"Beendet (Bestwert gesetzt!)" if not is_cancelled else "Abgebrochen (Bestwert gesetzt!)"
    else:
        set_system_settings(bitaxe_ip, def_v, def_f)
        final_msg = "Beendet (Standardwerte wiederhergestellt)" if not is_cancelled else "Abgebrochen"
        
    fire_update(hass, entry_id, final_msg, 100, state["best_mhz"], state["best_mv"])
