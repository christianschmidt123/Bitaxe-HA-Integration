import os
import json
import time
import logging
import requests
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# orginal: https://github.com/mrv777/Bitaxe-Hashrate-Benchmark/tree/main
# Konfiguration des Benchmarks
VOLTAGE_INCREMENT = 20
FREQUENCY_INCREMENT = 25
SLEEP_TIME = 90               # Zeit für Systemstabilisierung nach Reboot
BENCHMARK_TIME = 600          # 10 Minuten pro Schritt
SAMPLE_INTERVAL = 15          # 15 Sekunden Sample-Intervall
MAX_TEMP = 66                 
MAX_ALLOWED_VOLTAGE = 1400    
MAX_ALLOWED_FREQUENCY = 1200  
MAX_VR_TEMP = 86              
MIN_INPUT_VOLTAGE = 4800      
MAX_INPUT_VOLTAGE = 5500      
MAX_POWER = 40                
MIN_ALLOWED_VOLTAGE = 1000  
MIN_ALLOWED_FREQUENCY = 400  

STATUS_FILE_NAME = "bitaxe_benchmark_status.json"

def get_status_file_path(hass: HomeAssistant, entry_id: str) -> str:
    """Gibt den Pfad zur persistenten Statusdatei im HA .storage Ordner zurück."""
    return hass.config.path(".storage", f"{entry_id}_{STATUS_FILE_NAME}")

def load_benchmark_status(hass: HomeAssistant, entry_id: str):
    """Lädt den gespeicherten Zustand, falls vorhanden."""
    path = get_status_file_path(hass, entry_id)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            _LOGGER.error("Fehler beim Laden der Benchmark-Statusdatei: %s", e)
    return None

def save_benchmark_status(hass: HomeAssistant, entry_id: str, data: dict):
    """Speichert den aktuellen Zustand im HA .storage Ordner."""
    path = get_status_file_path(hass, entry_id)
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        _LOGGER.error("Fehler beim Speichern der Benchmark-Statusdatei: %s", e)

def fire_update(hass: HomeAssistant, entry_id: str, status: str, progress: float = 0.0, best_mhz: int = None, best_mv: int = None):
    """Sendet Status-Updates an die Sensor-Ebene der Integration."""
    hass.loop.call_soon_threadsafe(
        hass.bus.fire,
        f"bitaxe_bench_update_{entry_id}",
        {
            "status": status,
            "progress": round(progress, 1),
            "best_mhz": best_mhz,
            "best_mv": best_mv
        }
    )

def fetch_device_specs(bitaxe_ip):
    """Ermittelt Core-Counts und Standardwerte des Miners."""
    try:
        res = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
        res.raise_for_status()
        info = res.json()
        small_core_count = info.get("smallCoreCount")
        
        # Fallback auf /asic falls Daten unvollständig
        res_asic = requests.get(f"{bitaxe_ip}/api/system/asic", timeout=10)
        asic_info = res_asic.json() if res_asic.status_code == 200 else {}
        
        default_voltage = info.get("coreVoltage", asic_info.get("defaultVoltage", 1150))
        default_frequency = info.get("frequency", asic_info.get("defaultFrequency", 500))
        asic_count = info.get("asicCount", asic_info.get("asicCount", 1))
        
        return small_core_count, asic_count, default_voltage, default_frequency
    except Exception as e:
        _LOGGER.error("Fehler beim Abrufen der Bitaxe Specs: %s", e)
        raise e

def set_system_settings(bitaxe_ip, core_voltage, frequency):
    """Sendet Einstellungen und startet den Miner neu."""
    try:
        settings = {"coreVoltage": core_voltage, "frequency": frequency}
        res = requests.patch(f"{bitaxe_ip}/api/system", json=settings, timeout=10)
        res.raise_for_status()
        time.sleep(2)
        requests.post(f"{bitaxe_ip}/api/system/restart", timeout=10)
    except Exception as e:
        _LOGGER.error("Fehler beim Setzen der Bitaxe-Parameter: %s", e)

def run_benchmark_step(bitaxe_ip, core_voltage, frequency, small_core_count, asic_count):
    """Führt eine einzelne Frequenz/Spannungsstufe aus."""
    hash_rates, temperatures, power_consumptions, vr_temps = [], [], [], []
    total_samples = BENCHMARK_TIME // SAMPLE_INTERVAL
    expected_hashrate = frequency * ((small_core_count * asic_count) / 1000)

    for sample in range(total_samples):
        try:
            res = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
            if res.status_code != 200:
                continue
            info = res.json()
            
            temp = info.get("temp")
            vr_temp = info.get("vrTemp")
            voltage = info.get("voltage")
            hash_rate = info.get("hashRate")
            power = info.get("power")
            
            if temp is None or hash_rate is None or power is None:
                continue
                
            if temp >= MAX_TEMP or (vr_temp and vr_temp >= MAX_VR_TEMP):
                return None, "THERMAL_LIMIT"
            if voltage and (voltage < MIN_INPUT_VOLTAGE or voltage > MAX_INPUT_VOLTAGE):
                return None, "INPUT_VOLTAGE_FAULT"
            if power > MAX_POWER:
                return None, "POWER_LIMIT"

            hash_rates.append(hash_rate)
            temperatures.append(temp)
            power_consumptions.append(power)
            if vr_temp:
                vr_temps.append(vr_temp)
                
        except Exception:
            pass
        time.sleep(SAMPLE_INTERVAL)

    if len(hash_rates) < 7:
        return None, "TOO_FEW_SAMPLES"

    # Trimming analog zum Originalskript
    trimmed_hashrates = sorted(hash_rates)[3:-3]
    avg_hashrate = sum(trimmed_hashrates) / len(trimmed_hashrates)
    avg_power = sum(power_consumptions) / len(power_consumptions)
    
    if avg_hashrate <= 0:
        return None, "ZERO_HASHRATE"
        
    efficiency = avg_power / (avg_hashrate / 1000)
    hashrate_ok = (avg_hashrate >= expected_hashrate * 0.94)

    return {
        "coreVoltage": core_voltage,
        "frequency": frequency,
        "averageHashRate": avg_hashrate,
        "efficiencyJTH": efficiency,
        "hashrate_ok": hashrate_ok
    }, None

def run_bitaxe_benchmark(hass: HomeAssistant, entry_id: str, ip_address: str, initial_voltage: int = 1150, initial_frequency: int = 500):
    """Die Hauptschleife des Benchmarks. Unterstützt automatischen Resume."""
    bitaxe_ip = f"http://{ip_address}"
    
    try:
        small_core_count, asic_count, def_v, def_f = fetch_device_specs(bitaxe_ip)
    except Exception:
        fire_update(hass, entry_id, "Fehler: Verbindung fehlgeschlagen")
        return

    # Zustand laden oder neu initialisieren
    state = load_benchmark_status(hass, entry_id)
    if not state:
        state = {
            "current_voltage": initial_voltage,
            "current_frequency": initial_frequency,
            "results": [],
            "best_mhz": None,
            "best_mv": None,
            "is_running": True
        }
        save_benchmark_status(hass, entry_id, state)

    fire_update(hass, entry_id, "Läuft (Bereite vor...)", 0)
    
    while state["current_voltage"] <= MAX_ALLOWED_VOLTAGE and state["current_frequency"] <= MAX_ALLOWED_FREQUENCY:
        # Berechne groben prozentualen Fortschritt
        progress = ((state["current_voltage"] - initial_voltage) / (MAX_ALLOWED_VOLTAGE - initial_voltage + 1)) * 100
        fire_update(
            hass, entry_id, 
            f"Teste {state['current_frequency']}MHz @ {state['current_voltage']}mV", 
            progress, state["best_mhz"], state["best_mv"]
        )
        
        # Einstellen & Stabilisieren lassen
        set_system_settings(bitaxe_ip, state["current_voltage"], state["current_frequency"])
        time.sleep(SLEEP_TIME)
        
        res, err = run_benchmark_step(bitaxe_ip, state["current_voltage"], state["current_frequency"], small_core_count, asic_count)
        
        if res:
            state["results"].append(res)
            # Finde aktuellen Bestwert (höchste Hashrate)
            best = sorted(state["results"], key=lambda x: x["averageHashRate"], reverse=True)[0]
            state["best_mhz"] = best["frequency"]
            state["best_mv"] = best["coreVoltage"]
            
            if res["hashrate_ok"]:
                if state["current_frequency"] + FREQUENCY_INCREMENT <= MAX_ALLOWED_FREQUENCY:
                    state["current_frequency"] += FREQUENCY_INCREMENT
                else:
                    break
            else:
                if state["current_voltage"] + VOLTAGE_INCREMENT <= MAX_ALLOWED_VOLTAGE:
                    state["current_voltage"] += VOLTAGE_INCREMENT
                    state["current_frequency"] -= FREQUENCY_INCREMENT
                else:
                    break
        else:
            _LOGGER.info(f"Benchmark Limit erreicht wegen: {err}. Beende Schleife.")
            break
            
        save_benchmark_status(hass, entry_id, state)

    # Abschluss des Benchmarks: Bestwerte dauerhaft setzen
    if state["best_mhz"] and state["best_mv"]:
        fire_update(hass, entry_id, "Wende Bestwerte an...", 95, state["best_mhz"], state["best_mv"])
        set_system_settings(bitaxe_ip, state["best_mv"], state["best_mhz"])
        time.sleep(SLEEP_TIME)
        fire_update(hass, entry_id, "Abgeschlossen", 100, state["best_mhz"], state["best_mv"])
    else:
        fire_update(hass, entry_id, "Abgeschlossen (Keine Werte)", 100)
        set_system_settings(bitaxe_ip, def_v, def_f)

    # Statusdatei aufräumen bzw. abschließen
    state["is_running"] = False
    save_benchmark_status(hass, entry_id, state)
