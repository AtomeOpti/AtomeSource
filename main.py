# ============================================================
# BOOTSTRAP ROBUSTE
# Le programme vérifie les dépendances avant de créer l'interface.
# ============================================================
import sys
import subprocess
import re
from pathlib import Path

def _ensure_dependencies():
    packages = {
        "customtkinter": "customtkinter",
        "PIL": "Pillow",
        "psutil": "psutil",
        "requests": "requests",
    }
    missing = []
    for module, package in packages.items():
        try:
            __import__(module)
        except Exception:
            missing.append(package)

    if not missing:
        return

    # Installe uniquement dans le même environnement Python que celui
    # utilisé pour lancer main.py.
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-input"
    ] + missing

    try:
        subprocess.check_call(cmd)
    except Exception as exc:
        raise RuntimeError(
            "Dépendances Python manquantes.\n\n"
            "Impossible d'installer automatiquement : "
            + ", ".join(missing)
            + f"\n\nPython utilisé : {sys.executable}\n"
            f"Détail : {exc}"
        )

_ensure_dependencies()

# ============================================================
# NOTE — DÉPÔT SOURCE PUBLIC (LECTURE SEULE)
# ------------------------------------------------------------
# Ce dépôt est publié à titre de démonstration / transparence du
# fonctionnement d'AtomeOpti. Il ne contient volontairement pas
# le module privé "atomeopti_build" (identité de build, ressources
# de packaging), qui n'est présent que sur la machine/CI de build
# officielle. Sans ce module, l'application ne démarre pas depuis
# ces sources.
#
# => Pour utiliser AtomeOpti, télécharge la version compilée et
#    signée sur le site officiel : voir README.md.
# ============================================================
try:
    from atomeopti_build import BUILD_CHANNEL  # noqa: F401  (module privé, non fourni)
except ImportError as exc:
    raise SystemExit(
        "Ce dépôt est fourni à titre de code source de référence uniquement.\n"
        "Il ne peut pas être compilé ou exécuté tel quel : il lui manque le "
        "module de build privé (atomeopti_build), qui n'est pas distribué "
        "publiquement.\n\n"
        "Pour utiliser AtomeOpti, télécharge la version officielle sur le "
        "site : voir le README.md de ce dépôt."
    ) from exc

import customtkinter as ctk
from PIL import Image, ImageEnhance
import platform
import os
import hashlib
import ctypes
import psutil
import threading
import queue
import zipfile
from urllib.request import Request, urlopen
from urllib.parse import urljoin
import json
import requests
from tkinter import messagebox
import webbrowser

ctk.set_appearance_mode("dark")
# ?? Emojis colorés dans toute l'interface.
# Windows choisit la police emoji disponible ; Segoe UI Emoji est privilégiée.
try:
    EMOJI_FONT = ("Segoe UI Emoji", 22)
    EMOJI_SMALL_FONT = ("Segoe UI Emoji", 18)
except Exception:
    EMOJI_FONT = ("Arial", 22)
    EMOJI_SMALL_FONT = ("Arial", 18)

EMOJI_MENU = {
    "Accueil": "??",
    "Apps": "??",
    "Windows": "??",
    "Désinstallation": "???",
    "Nettoyage": "??",
    "Démarrage": "??",
}

def emoji_label(parent, emoji, text, **kwargs):
    """Label visuel avec emoji séparé pour conserver l'aspect coloré."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame._emoji_widget = ctk.CTkLabel(
        frame, text=emoji, font=EMOJI_FONT,
        width=34, text_color="#FFFFFF"
    )
    frame._emoji_widget.pack(side="left", padx=(0, 8))
    frame._text_widget = ctk.CTkLabel(frame, text=text, **kwargs)
    frame._text_widget.pack(side="left")
    return frame


# ============================================================
# IDENTITÉ VISUELLE ATOMEOPTI
# Inspirée directement du logo fourni : bleu électrique + orange
# sur fond noir / graphite.
# ============================================================
BACKGROUND = "#070511"
SIDEBAR = "#0A0616"
CARD = "#100A20"
CARD_ALT = "#160D2A"
BORDER = "#2A1748"
BORDER_BLUE = "#6B2CFF"
BLUE = "#8B3DFF"
BLUE_BRIGHT = "#B56CFF"
BLUE_HOVER = "#A65BFF"
ORANGE = "#FF4FD8"
ORANGE_BRIGHT = "#FF78E6"
PURPLE = "#8B3DFF"
PURPLE_HOVER = "#A65BFF"
TEXT = "#F8F2FF"
MUTED = "#A79BB8"
SUCCESS = "#62F6B5"

APP_DIR = Path(__file__).resolve().parent
LOGO_BANNER_PATH = APP_DIR / "performance_pc_banner.png"
LOGO_BRAND_PATH = APP_DIR / "performance_pc_brand.png"
EMOJI_ASSETS_DIR = APP_DIR / "assets" / "emoji"
COMPONENT_ASSETS_DIR = APP_DIR / "assets"
COMPONENT_ASSET_FILES = {
    "cpu.png": "cpu-no-ring.png",
    "ram.png": "ram-no-ring.png",
    "gpu.png": "gpu-no-ring-v2.png",
    "ssd.png": "ssd-no-ring-v2.png",
}

# Tkinter rend fréquemment les émojis texte en monochrome sous Windows.
# Ces fichiers PNG conservent donc les icônes colorées dans l'interface.
MENU_ICON_FILES = {
    "Accueil": "pc.png",
    "Apps": "apps.png",
    "Windows": "windows.png",
    "Désinstallation": "trash.png",
    "Nettoyage": "clean.png",
    "Démarrage": "rocket.png",
}


def _hidden_startupinfo():
    """STARTUPINFO Windows qui empêche toute fenêtre console de s'afficher."""
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    return startup


def powershell(command):
    try:
        return subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-Command", command],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        ).strip()
    except Exception:
        return ""


def winget_installed(package_id):
    """Retourne True si Winget indique que le paquet est déjà installé."""
    try:
        result = subprocess.run(
            ["winget", "list", "--id", package_id, "--exact",
             "--accept-source-agreements", "--disable-interactivity"],
            capture_output=True,
            text=True,
            timeout=20,
            startupinfo=_hidden_startupinfo(),
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0 and package_id.lower() in result.stdout.lower()
    except Exception:
        return False


def install_winget_package(package_id):
    """Installe un paquet Winget sans bloquer l'interface."""
    try:
        return subprocess.run(
            [
                "winget", "install",
                "--id", package_id,
                "--exact",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--disable-interactivity"
            ],
            capture_output=True,
            text=True,
            timeout=300,
            startupinfo=_hidden_startupinfo(),
            creationflags=subprocess.CREATE_NO_WINDOW
        ).returncode == 0
    except Exception:
        return False


def get_cpu_name():
    """Retourne le vrai nom marketing du processeur, pas l'architecture AMD64."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            if name and str(name).strip():
                return str(name).strip()
    except Exception:
        pass
    result = powershell("(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)")
    if result:
        return result.splitlines()[0].strip()
    return "Processeur non détecté"


APP_CATALOG = [
    {
        "name": "ParkControl",
        "category": "CPU · Bitsum",
        "description": "Ajuste le parking des coeurs CPU et les fréquences pour réduire la latence.",
        "package": "BitSum.ParkControl",
    },
    {
        "name": "Process Lasso",
        "category": "CPU · Bitsum",
        "description": "Automatisation des processus, priorités CPU et anti-throttling.",
        "package": "BitSum.ProcessLasso",
    },
    {
        "name": "Driver Booster 13",
        "category": "Pilotes · IObit",
        "description": "Détecte et met à jour les pilotes en un clic.",
        "package": "IObit.DriverBooster",
    },
    {
        "name": "MSI Afterburner",
        "category": "GPU · MSI/Guru3D",
        "description": "Monitoring GPU, courbes de ventilateurs et overclocking.",
        "package": "Guru3D.Afterburner",
    },
    {
        "name": "MSI Utility v3",
        "category": "Latence · GitHub",
        "description": "Active le mode MSI (Message Signaled Interrupts) sur les périphériques PCIe.",
        "package": "GITHUB_DOWNLOAD",
        "download_url": "https://github.com/Sathango/Msi-Utility-v3/raw/main/Msi%20Utility%20v3.exe?download=1",
    },
    {
        "name": "Wintoys",
        "category": "Optimisation · Microsoft Store",
        "description": "Outil tout-en-un pour optimiser Windows : tweaks, nettoyage et performance.",
        "package": "9P8LTPGCBZXD",
    },
    {
        "name": "Polling Rate",
        "category": "Latence · GitHub",
        "description": "Pilote HIDUSBF pour ajuster le polling rate des périphériques HID.",
        "package": "LOCAL_ZIP",
        "zip_name": "hidusbf.zip",
        "exe_path": "DRIVER/Setup.exe",
    },
    {
        "name": "Interrupt Affinity Tool",
        "category": "Latence · GitHub",
        "description": "Configure l'affinité des interruptions CPU (IRQ) et le mode MSI.",
        "package": "LOCAL_ZIP",
        "zip_name": "Interrupt_Affinity_Policy_Tool.zip",
        "exe_path": "intPolicy_x64.exe",
    },
    {
        "name": "AutoGpuAffinity",
        "category": "GPU · GitHub",
        "description": "Configure automatiquement l'affinité GPU des applications.",
        "package": "GITHUB_ZIP",
        "repo": "valleyofdoom/AutoGpuAffinity",
        "exe_name": "AutoGpuAffinity.exe",
    },
    {
        "name": "LatencyMon",
        "category": "Latence · Resplendence",
        "description": "Analyse la latence DPC/ISR et les pilotes responsables.",
        "package": "Resplendence.LatencyMon",
    },
    {
        "name": "Core Temp",
        "category": "Monitoring · CPU",
        "description": "Surveille la température du processeur en temps réel et les informations détaillées des cœurs CPU.",
        "package": "ALCPU.CoreTemp",
    },
]

APP_ICON_FILES = {
    # Logos officiels fournis dans assets/ (les extensions sont conservées).
    "ParkControl": "park.control.jpg", "Process Lasso": "process.lasso.png",
    "Driver Booster 13": "driver.booster.png", "MSI Afterburner": "msi.afterburner.png",
    "MSI Utility v3": "msi.utility.jpg", "Wintoys": "wintoys.png",
    "Polling Rate": "hidusbf.webp", "Interrupt Affinity Tool": "affinity.jpg",
    "AutoGpuAffinity": "autogpuaffinity.jpg", "LatencyMon": "performance.png",
    "Core Temp": "temperature.png",
}

UNINSTALL_ICON_FILES = {
    "Copilot": "performance.png", "Microsoft Teams": "apps.png",
    "Microsoft OneDrive": "pc.png", "Actualités": "apps.png",
    "Météo": "windows.png", "Cartes": "pc.png", "Xbox": "gaming.png",
    "Xbox Game Bar": "gaming.png", "Paint": "settings.png",
}


def get_gpu_name():
    result = powershell(
        "Get-CimInstance Win32_VideoController | "
        "Select-Object -ExpandProperty Name"
    )
    names = [x.strip() for x in result.splitlines() if x.strip()]
    return names[0] if names else "Carte graphique non détectée"


def get_ram_configuration():
    """Retourne les barrettes détectées et le nombre total d'emplacements RAM."""
    modules = []
    slots = 0
    try:
        result = powershell(
            "Get-CimInstance Win32_PhysicalMemory | ForEach-Object { "
            "'{0}|{1}|{2}' -f $_.DeviceLocator, $_.BankLabel, $_.Capacity }"
        )
        for line in result.splitlines():
            fields = [field.strip() for field in line.split("|")]
            if len(fields) != 3:
                continue
            try:
                size_gb = int(fields[2]) / 1024**3
            except (TypeError, ValueError):
                size_gb = 0
            raw_position = fields[0] or fields[1] or ""
            # Les fabricants exposent souvent « DIMM1…DIMM4 ». On affiche
            # les emplacements usuels de la carte mère : A1, A2, B1, B2.
            dimm = re.search(r"DIMM\s*[-_ ]?(\d+)", raw_position, re.I)
            if dimm:
                index = int(dimm.group(1))
                position = {1: "A1", 2: "A2", 3: "B1", 4: "B2"}.get(
                    index, f"Slot {index}"
                )
            else:
                channel = re.search(r"(?:CHANNEL|BANK)\s*([AB])", raw_position, re.I)
                number = re.search(r"(?:DIMM|SLOT|BANK)\s*[-_ ]?(\d+)", raw_position, re.I)
                position = (
                    f"{channel.group(1).upper()}{int(number.group(1)) + 1}"
                    if channel and number else raw_position
                ) or f"A{len(modules) + 1}"
            modules.append({"position": position, "size_gb": size_gb})

        value = powershell(
            "Get-CimInstance Win32_PhysicalMemoryArray | "
            "Select-Object -First 1 -ExpandProperty MemoryDevices"
        )
        slots = int(value.splitlines()[0]) if value else 0
    except Exception:
        pass
    return modules, max(slots, len(modules))



_coretemp_started = False

class _CoreTempSharedDataEx(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("uiLoad", ctypes.c_uint32 * 256),
        ("uiTjMax", ctypes.c_uint32 * 128),
        ("uiCoreCnt", ctypes.c_uint32),
        ("uiCPUCnt", ctypes.c_uint32),
        ("fTemp", ctypes.c_float * 256),
        ("fVID", ctypes.c_float),
        ("fCPUSpeed", ctypes.c_float),
        ("fFSBSpeed", ctypes.c_float),
        ("fMultiplier", ctypes.c_float),
        ("sCPUName", ctypes.c_char * 100),
        ("ucFahrenheit", ctypes.c_ubyte),
        ("ucDeltaToTjMax", ctypes.c_ubyte),
        ("ucTdpSupported", ctypes.c_ubyte),
        ("ucPowerSupported", ctypes.c_ubyte),
        ("uiStructVersion", ctypes.c_uint32),
        ("uiTdp", ctypes.c_uint32 * 128),
        ("fPower", ctypes.c_float * 128),
        ("fMultipliers", ctypes.c_float * 256),
    ]


def find_coretemp_exe():
    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Core Temp" / "Core Temp.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Core Temp" / "Core Temp.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Core Temp" / "Core Temp.exe",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def ensure_coretemp_running():
    global _coretemp_started

    if _coretemp_started:
        return

    try:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() == "core temp.exe":
                _coretemp_started = True
                return
    except Exception:
        pass

    exe = find_coretemp_exe()
    if exe is None:
        return

    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            startupinfo=_hidden_startupinfo(),
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        _coretemp_started = True
    except Exception:
        pass


def read_coretemp_temperature():
    # Lit CoreTempMappingObjectEx, l'interface Shared Memory officielle de Core Temp.
    ensure_coretemp_running()

    # Attente nécessaire pour laisser Core Temp créer la mémoire partagée
    import time
    time.sleep(2)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    OpenFileMappingW = kernel32.OpenFileMappingW
    OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    OpenFileMappingW.restype = ctypes.c_void_p

    MapViewOfFile = kernel32.MapViewOfFile
    MapViewOfFile.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t
    ]
    MapViewOfFile.restype = ctypes.c_void_p

    UnmapViewOfFile = kernel32.UnmapViewOfFile
    UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    UnmapViewOfFile.restype = ctypes.c_int

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.c_void_p]
    CloseHandle.restype = ctypes.c_int

    FILE_MAP_READ = 0x0004

    for mapping_name in ("CoreTempMappingObjectEx", "CoreTempMappingObject"):
        handle = OpenFileMappingW(FILE_MAP_READ, False, mapping_name)
        if not handle:
            continue

        view = MapViewOfFile(
            handle, FILE_MAP_READ, 0, 0,
            ctypes.sizeof(_CoreTempSharedDataEx)
        )
        if not view:
            CloseHandle(handle)
            continue

        try:
            raw = ctypes.string_at(view, ctypes.sizeof(_CoreTempSharedDataEx))
            data = _CoreTempSharedDataEx.from_buffer_copy(raw)

            count = int(data.uiCoreCnt)
            if count <= 0 or count > 256:
                count = 1

            temps = [
                float(data.fTemp[i])
                for i in range(count)
                if -100.0 < float(data.fTemp[i]) < 200.0
            ]
            if not temps:
                continue

            if data.ucDeltaToTjMax:
                tjmax = float(data.uiTjMax[0])
                temps = [tjmax - t for t in temps]

            value = max(temps)
            if data.ucFahrenheit:
                value = (value - 32.0) * 5.0 / 9.0

            if 0 <= value <= 120:
                return value
        except Exception:
            pass
        finally:
            UnmapViewOfFile(view)
            CloseHandle(handle)

    return None


def get_cpu_temperature():
    """Récupère la température CPU avec plusieurs sources de secours."""

    try:
        result = powershell(
            """
            Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor `
            -ErrorAction SilentlyContinue |
            Where-Object {
                $_.SensorType -eq "Temperature" -and
                $_.Name -match "CPU|Package|Core|Tctl|Tdie"
            } |
            Select-Object -First 1 -ExpandProperty Value
            """
        )

        if result:
            return float(result.split()[0])

    except Exception:
        pass

    # Certaines installations exposent OpenHardwareMonitor au lieu de LHM.
    try:
        result = powershell(
            "Get-CimInstance -Namespace root/OpenHardwareMonitor -ClassName Sensor "
            "-ErrorAction SilentlyContinue | Where-Object { $_.SensorType -eq "
            "'Temperature' -and $_.Name -match 'CPU|Package|Core|Tctl|Tdie' } | "
            "Select-Object -First 1 -ExpandProperty Value"
        )
        if result:
            return float(result.split()[0])
    except Exception:
        pass

    # Core Temp est déjà pris en charge par l'application : il n'était
    # simplement jamais utilisé comme solution de repli.
    try:
        return read_coretemp_temperature()
    except Exception:
        pass

    return None

def get_gpu_stats():
    usage = None
    temperature = None

    try:
        result = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        ).strip()
        if result:
            values = [x.strip() for x in result.splitlines()[0].split(",")]
            usage = float(values[0]) if values else None
            temperature = float(values[1]) if len(values) > 1 else None
            return usage, temperature
    except Exception:
        pass

    # Repli matériel : LibreHardwareMonitor/OpenHardwareMonitor expose la
    # charge et la température sur les GPU AMD, Intel et NVIDIA sans nvidia-smi.
    try:
        sensor_script = r"""
        $s = Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor -ErrorAction SilentlyContinue
        if (-not $s) { $s = Get-CimInstance -Namespace root/OpenHardwareMonitor -ClassName Sensor -ErrorAction SilentlyContinue }
        $s | Where-Object { $_.Name -match 'GPU|Core|Temperature' -and $_.SensorType -match 'Load|Temperature' } |
          ForEach-Object { '{0}|{1}|{2}' -f $_.SensorType,$_.Name,$_.Value }
        """
        for line in powershell(sensor_script).splitlines():
            parts = [x.strip() for x in line.split("|", 2)]
            if len(parts) != 3:
                continue
            try:
                value = float(parts[2].replace(",", "."))
            except ValueError:
                continue
            sensor_type, name = parts[0].lower(), parts[1].lower()
            if temperature is None and "temperature" in sensor_type and "gpu" in name:
                temperature = value
            if usage is None and "load" in sensor_type and "gpu" in name:
                usage = max(0.0, min(100.0, value))
    except Exception:
        pass

    try:
        result = powershell(
            "(Get-Counter '\\GPU Engine(*)\\Utilization Percentage').CounterSamples "
            "| Where-Object {$_.CookedValue -gt 0} "
            "| Measure-Object -Property CookedValue -Maximum "
            "| Select-Object -ExpandProperty Maximum"
        )
        if result:
            usage = max(0, min(100, float(result.splitlines()[0])))
    except Exception:
        pass

    return usage, temperature


def get_cpu_frequency():
    freq = psutil.cpu_freq()
    return freq.current / 1000 if freq else None


def temp_text(value):
    return "N/D" if value is None else f"{value:.0f} °C"



def start_hardware_monitor():
    """Lance LibreHardwareMonitor en arrière-plan si présent."""

    import subprocess
    from pathlib import Path

    monitor = (
        Path.home()
        / "AppData"
        / "Local"
        / "PerformancePC"
        / "LibreHardwareMonitor"
        / "LibreHardwareMonitor.exe"
    )

    if monitor.exists():
        try:
            subprocess.Popen(
                [str(monitor)],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass


class PerformancePC(ctk.CTk):

    def __init__(self, free=False, premium=False):
        super().__init__()

        self.title("AtomeOpti • Centre de contrôle")
        self.geometry("1520x920")
        self.minsize(1280, 820)
        self.configure(fg_color=BACKGROUND)

        # État de la licence Premium pour cette session.
        self.free_active = free
        self.premium_active = premium

        self.free_key = None
        self.premium_key = None
        self.license_server_url = os.getenv(
            "LICENSE_SERVER_URL", "http://127.0.0.1:8000"
        ).rstrip("/")

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.create_sidebar()
        self.create_main()

        # ??? Lance LibreHardwareMonitor automatiquement
        start_hardware_monitor()

        # Les informations matériel doivent exister AVANT show_home(),
        # car la page d'accueil les affiche immédiatement.
        # L'ancien code les initialisait seulement dans start_monitoring(),
        # qui était appelé après la création de la page : AttributeError.
        try:
            self.cpu_name = get_cpu_name() or "Processeur inconnu"
        except Exception:
            self.cpu_name = "Processeur inconnu"

        try:
            self.gpu_name = get_gpu_name() or "Carte graphique inconnue"
        except Exception:
            self.gpu_name = "Carte graphique inconnue"

        self.ram_modules, self.ram_slot_count = get_ram_configuration()

        self.show_home()

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, width=252, corner_radius=0, fg_color=SIDEBAR,
            border_width=0
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # ----------------------------------------------------
        # Branding
        # ----------------------------------------------------
        brand = ctk.CTkFrame(
            self.sidebar,
            fg_color="#0D081A",
            corner_radius=16,
            border_width=1,
            border_color="#5A22B8"
        )
        brand.pack(fill="x", padx=12, pady=(14, 16))

        self._logo_images = {}
        if LOGO_BRAND_PATH.exists():
            try:
                img = Image.open(LOGO_BRAND_PATH).convert("RGB")
                img = ImageEnhance.Contrast(img).enhance(1.06)
                img = ImageEnhance.Sharpness(img).enhance(1.12)
                self._logo_images["brand"] = ctk.CTkImage(
                    light_image=img, dark_image=img, size=(230, 112)
                )
                ctk.CTkLabel(
                    brand, image=self._logo_images["brand"], text=""
                ).pack(padx=8, pady=(8, 4))
            except Exception:
                pass

        ctk.CTkLabel(
            brand,
            text="??? MONTAGE • ? OPTIMISATION • ?? GAMING",
            text_color=ORANGE_BRIGHT,
            font=ctk.CTkFont(size=8, weight="bold")
        ).pack(pady=(0, 10))

        # Petit indicateur de statut
        status = ctk.CTkFrame(
            brand, fg_color="#160D28", corner_radius=9
        )
        status.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(
            status, text="?", text_color=SUCCESS,
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left", padx=(10, 4), pady=7)

        ctk.CTkLabel(
            status, text="? SYSTÈME PRÊT",
            text_color="#D8C8EA",
            font=ctk.CTkFont(size=9, weight="bold")
        ).pack(side="left", pady=7)

        self.menu_buttons = {}
        self._menu_icon_images = {}

        ctk.CTkLabel(
            self.sidebar, text="NAVIGATION",
            text_color="#8C79A4",
            font=ctk.CTkFont(size=9, weight="bold")
        ).pack(anchor="w", padx=18, pady=(0, 7))

        self.add_menu("??", "Accueil", self.show_home)
        self.add_menu("??", "Apps", self.show_apps)
        self.add_menu("?", "Windows", self.show_windows)
        self.add_menu("???", "Désinstallation", self.show_uninstall)
        self.add_menu("??", "Nettoyage", self.show_cleaner)
        self.add_menu("??", "Démarrage", self.show_startup)

        ctk.CTkFrame(
            self.sidebar, fg_color="transparent"
        ).pack(expand=True, fill="both")

        # ----------------------------------------------------
        # Carte AtomeOpti
        # ----------------------------------------------------
        premium = ctk.CTkFrame(
            self.sidebar,
            fg_color="#10081F",
            corner_radius=15,
            border_width=1,
            border_color=BORDER
        )
        premium.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(
            premium, text="ATOMEOPTI",
            text_color=BLUE_BRIGHT,
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(anchor="w", padx=14, pady=(13, 3))

        ctk.CTkLabel(
            premium,
            text="Centre de contrôle gaming",
            text_color=MUTED,
            font=ctk.CTkFont(size=9)
        ).pack(anchor="w", padx=14, pady=(0, 8))

        ctk.CTkButton(
            premium, text="Activation",
            height=36, corner_radius=9,
            fg_color="#211038", hover_color="#3B1767",
            border_width=1, border_color="#5A22B8",
            text_color="#F1E5FF",
            command=self.show_premium_activation
        ).pack(fill="x", padx=10, pady=4)

        ctk.CTkButton(
            premium, text="Relancer en admin",
            height=36, corner_radius=9,
            fg_color=BLUE, hover_color=BLUE_HOVER,
            text_color="white",
            command=self.restart_as_admin
        ).pack(fill="x", padx=10, pady=(4, 12))

    def add_menu(self, icon, text, command):
        image = None
        icon_path = EMOJI_ASSETS_DIR / MENU_ICON_FILES.get(text, "")
        if icon_path.is_file():
            try:
                source = Image.open(icon_path).convert("RGBA")
                image = ctk.CTkImage(
                    light_image=source, dark_image=source, size=(23, 23)
                )
                # Conserver une référence empêche Tkinter de supprimer l'image.
                self._menu_icon_images[text] = image
            except Exception:
                image = None

        button = ctk.CTkButton(
            self.sidebar,
            text=text if image else f"{icon} {text}",
            image=image,
            compound="left",
            height=43,
            corner_radius=10,
            anchor="w",
            fg_color="transparent",
            hover_color="#24123D",
            text_color="#D4C8E3",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=command
        )
        button.pack(fill="x", padx=12, pady=(1,1))
        self.menu_buttons[text] = button

    def colored_icon(self, filename, size=(28, 28)):
        """Charge une icône PNG colorée et conserve sa référence Tkinter."""
        cache_key = (filename, size)
        if not hasattr(self, "_colored_icon_cache"):
            self._colored_icon_cache = {}
        if cache_key not in self._colored_icon_cache:
            # Les logos applicatifs sont stockés directement dans assets/,
            # tandis que les icônes d'interface restent dans assets/app_icons/.
            # Chercher d'abord dans le dossier composants permet d'utiliser les
            # fichiers réels (PNG/JPG/WebP) référencés par APP_ICON_FILES.
            path = COMPONENT_ASSETS_DIR / filename
            if not path.is_file():
                path = EMOJI_ASSETS_DIR / filename
            if not path.is_file():
                return None
            try:
                source = Image.open(path).convert("RGBA")
                self._colored_icon_cache[cache_key] = ctk.CTkImage(
                    light_image=source, dark_image=source, size=size
                )
            except Exception:
                return None
        return self._colored_icon_cache[cache_key]

    def component_icon(self, filename, size):
        """Charge les vrais visuels des composants, distincts des émojis UI."""
        cache_key = ("component", filename, size)
        if not hasattr(self, "_colored_icon_cache"):
            self._colored_icon_cache = {}
        if cache_key not in self._colored_icon_cache:
            path = COMPONENT_ASSETS_DIR / COMPONENT_ASSET_FILES.get(filename, filename)
            if not path.is_file():
                path = EMOJI_ASSETS_DIR / filename
            if not path.is_file():
                return None
            try:
                source = Image.open(path).convert("RGBA")
                self._colored_icon_cache[cache_key] = ctk.CTkImage(
                    light_image=source, dark_image=source, size=size
                )
            except Exception:
                return None
        return self._colored_icon_cache[cache_key]

    def add_page_title(self, parent, icon_file, title, size=28):
        """Ajoute un titre avec une vraie icône couleur, plutôt qu'un emoji texte."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", pady=(8, 4))
        image = self.colored_icon(icon_file, (size, size))
        if image:
            ctk.CTkLabel(row, image=image, text="").pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            row, text=title, font=ctk.CTkFont(size=size, weight="bold")
        ).pack(side="left")
        return row

    def create_visual_header(self, icon_file, title, subtitle, accent=PURPLE):
        """En-tête visuel commun pour les pages de gestion."""
        header = ctk.CTkFrame(
            self.content, fg_color="#110923", corner_radius=18,
            border_width=1, border_color=accent
        )
        header.pack(fill="x", pady=(4, 14))
        icon = self.colored_icon(icon_file, (42, 42))
        if icon:
            ctk.CTkLabel(header, image=icon, text="").pack(
                side="left", padx=(18, 12), pady=15
            )
        text = ctk.CTkFrame(header, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, pady=13)
        ctk.CTkLabel(
            text, text=title, text_color=TEXT,
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            text, text=subtitle, text_color=MUTED,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=(3, 0))
        ctk.CTkLabel(
            header, text="CENTRE DE CONTRÔLE", text_color=accent,
            font=ctk.CTkFont(size=9, weight="bold")
        ).pack(side="right", padx=18)
        return header

    def active_menu(self, name):
        for text, button in self.menu_buttons.items():
            if text == name:
                button.configure(
                    fg_color="#5120A8",
                    hover_color="#6B2CFF",
                    text_color="white"
                )
            else:
                button.configure(
                    fg_color="transparent",
                    text_color="#D4C8E3"
                )

    # --------------------------------------------------------
    # MAIN
    # --------------------------------------------------------

    def create_main(self):
        self.main = ctk.CTkFrame(
            self, fg_color=BACKGROUND, corner_radius=0
        )
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)

        self.content = ctk.CTkScrollableFrame(
            self.main,
            fg_color=BACKGROUND,
            scrollbar_button_color="#2B1648",
            scrollbar_button_hover_color="#6B2CFF"
        )
        self.content.grid(
            row=0, column=0, sticky="nsew", padx=22, pady=18
        )

    def clear_content(self):
        for widget in self.content.winfo_children():
            widget.destroy()

    # --------------------------------------------------------
    # ACCUEIL
    # --------------------------------------------------------

    def show_home(self):
        self.clear_content()
        self.active_menu("Accueil")

        # ----------------------------------------------------
        # En-tête premium
        # ----------------------------------------------------
        topbar = ctk.CTkFrame(self.content, fg_color="transparent")
        topbar.pack(fill="x", pady=(0, 10))

        title_box = ctk.CTkFrame(topbar, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)
        title_row = ctk.CTkFrame(
    title_box,
    fg_color="transparent"
)
        title_row.pack(anchor="w")


        self.wave_icon = self.colored_icon("rocket.png", (46, 46))


        ctk.CTkLabel(
            title_row,
            image=self.wave_icon,
            text=""
        ).pack(
            side="left",
            padx=(0, 10)
        )


        ctk.CTkLabel(
            title_row,
            text="Bienvenue sur AtomeOpti",
            text_color=TEXT,
            font=ctk.CTkFont(size=34, weight="bold")
        ).pack(
            side="left"
        )
        slogan = ctk.CTkFrame(title_box, fg_color="transparent")
        slogan.pack(anchor="w", pady=(2, 0))
        for icon_file, message in (
            ("settings.png", "Optimise ton système"),
            ("performance.png", "Gagne en performance"),
            ("gaming.png", "Domine tes jeux"),
        ):
            ctk.CTkLabel(
                slogan, image=self.colored_icon(icon_file, (20, 20)), text=""
            ).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                slogan, text=message, text_color=MUTED,
                font=ctk.CTkFont(size=13)
            ).pack(side="left", padx=(0, 20))

        # ----------------------------------------------------
        # Hero / logo principal
        # ----------------------------------------------------
        hero = ctk.CTkFrame(
            self.content,
            fg_color="#09051A",
            corner_radius=20,
            border_width=2,
            border_color="#A229FF"
        )
        hero.pack(fill="x", pady=(0, 14))
        hero.grid_columnconfigure(0, weight=1)

        if LOGO_BANNER_PATH.exists():
            try:
                img = Image.open(LOGO_BANNER_PATH).convert("RGB")
                img = ImageEnhance.Contrast(img).enhance(1.04)
                self._logo_images["banner"] = ctk.CTkImage(
                    light_image=img, dark_image=img, size=(1160, 390)
                )
                ctk.CTkLabel(
                    hero, image=self._logo_images["banner"], text=""
                ).pack(fill="x", padx=4, pady=4)
            except Exception:
                ctk.CTkLabel(
                    hero, text="ATOMEOPTI",
                    font=ctk.CTkFont(size=34, weight="bold"),
                    text_color="white"
                ).pack(pady=55)
        else:
            ctk.CTkLabel(
                hero, text="ATOMEOPTI",
                font=ctk.CTkFont(size=34, weight="bold"),
                text_color="white"
            ).pack(pady=50)
        # ----------------------------------------------------
        # Bannière de stats (connectée plus tard au site AtomeOpti)
        # ----------------------------------------------------
        self._stats_banner = ctk.CTkFrame(
            self.content,
            fg_color="#0D0820",
            corner_radius=16,
            border_width=1,
            border_color="#3A1F6B"
        )
        self._stats_banner.pack(fill="x", pady=(0, 14))

        banner_header = ctk.CTkFrame(self._stats_banner, fg_color="transparent")
        banner_header.pack(fill="x", padx=18, pady=(14, 8))

        ctk.CTkLabel(
            banner_header,
            text="STATISTIQUES ATOMEOPTI",
            text_color="#00C8FF",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(
            banner_header,
            text="En direct",
            text_color=MUTED,
            font=ctk.CTkFont(size=10)
        ).pack(side="right")

        banner_stats = ctk.CTkFrame(self._stats_banner, fg_color="transparent")
        banner_stats.pack(fill="x", padx=18, pady=(0, 14))

        for i in range(4):
            banner_stats.grid_columnconfigure(i, weight=1)

        self._banner_stat_labels = {}
        banner_stats_data = [
            ("downloads", "Téléchargements", "0"),
            ("active_users", "Utilisateurs actifs", "0"),
            ("optimizations", "Optimisations", "0"),
            ("rating", "Note moyenne", "5.0"),
        ]

        for idx, (key, label, value) in enumerate(banner_stats_data):
            stat_frame = ctk.CTkFrame(
                banner_stats, fg_color="#13092B",
                corner_radius=12, border_width=1,
                border_color="#2A1550"
            )
            stat_frame.grid(row=0, column=idx, sticky="nsew", padx=5, pady=2)

            ctk.CTkLabel(
                stat_frame, text=value,
                font=ctk.CTkFont(size=24, weight="bold"),
                text_color="#00C8FF"
            ).pack(anchor="w", padx=14, pady=(12, 2))

            ctk.CTkLabel(
                stat_frame, text=label,
                text_color=MUTED,
                font=ctk.CTkFont(size=11)
            ).pack(anchor="w", padx=14, pady=(0, 12))

            self._banner_stat_labels[key] = idx

        # ----------------------------------------------------
        # Statistiques
        # ----------------------------------------------------
        overview = ctk.CTkFrame(self.content, fg_color="transparent")
        overview.pack(anchor="w", pady=(2, 7))
        ctk.CTkLabel(
            overview, image=self.colored_icon("performance.png", (19, 19)), text=""
        ).pack(side="left", padx=(0, 7))
        ctk.CTkLabel(
            overview, text="APERÇU SYSTÈME", text_color="#B56CFF",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")

        cards = ctk.CTkFrame(
            self.content, fg_color="transparent"
        )
        cards.pack(fill="x")

        for i in range(4):
            cards.grid_columnconfigure(i, weight=1)

        self.cpu_card = self.create_stat_card(cards, 0, "cpu.png", "CPU")
        self.ram_card = self.create_stat_card(cards, 1, "ram.png", "Mémoire (RAM)")
        self.gpu_card = self.create_stat_card(cards, 2, "gpu.png", "GPU")
        self.disk_card = self.create_stat_card(cards, 3, "ssd.png", "Disque système")

        second = ctk.CTkFrame(
            self.content, fg_color="transparent"
        )
        second.pack(fill="x", pady=10)

        for i in range(4):
            second.grid_columnconfigure(i, weight=1)

        self.cpu_detail_card = self.create_small_card(
            second, 0, "cpu.png", "CPU", "Chargement..."
        )
        self.ram_detail_card = self.create_small_card(
            second, 1, "ram.png", "Barrettes RAM", "Chargement..."
        )
        self.disk_detail_card = self.create_small_card(
            second, 2, "ssd.png", "SSD / Disque", "Chargement..."
        )
        self.motherboard_detail_card = self.create_small_card(
            second, 3, "temperature.png", "Température", "Chargement..."
        )

        # Les informations importantes restent dans le même plan : état à
        # gauche, configuration détaillée à droite.
        bottom = ctk.CTkFrame(self.content, fg_color="transparent")
        bottom.pack(fill="x", pady=(5, 5))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)

        system = ctk.CTkFrame(
            bottom,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color=BORDER
        )
        system.pack(side="left", fill="both", expand=True, padx=(0, 5))

        header = ctk.CTkFrame(system, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 6))

        ctk.CTkLabel(
            header, image=self.colored_icon("pc.png", (19, 19)), text=""
        ).pack(side="left", padx=(0, 7))
        ctk.CTkLabel(
            header, text="ÉTAT DU SYSTÈME",
            text_color=BLUE_BRIGHT,
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="left")


        self.system_label = ctk.CTkLabel(
            system, text="Chargement...",
            text_color="#AEBCC9",
            justify="left"
        )
        self.system_label.pack(anchor="w", padx=55, pady=(0, 15))

        # ----------------------------------------------------
        # Informations système ???
        # ----------------------------------------------------
        info = ctk.CTkFrame(
            bottom,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color="#2E1850"
        )
        info.pack(side="left", fill="both", expand=True, padx=(5, 0))

        ctk.CTkLabel(
            info,
            text="INFORMATIONS SYSTÈME",
            text_color="#B56CFF",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=16, pady=(14, 9))

        self.home_info_label = ctk.CTkLabel(
            info,
            text=f"Système : {platform.system()} {platform.release()}\n"
                 f"Architecture : {platform.machine()}\n"
                 f"Processeur : {self.cpu_name}\n"
                 f"Carte graphique : {self.gpu_name}\n"
                 f"RAM : {'détectée' if self.ram_modules else 'N/D'}\n"
                 f"Emplacements : {', '.join(module['position'] for module in self.ram_modules) or 'inconnus'}",
            text_color="#C7BBD5",
            justify="left",
            anchor="w"
        )
        self.home_info_label.pack(anchor="w", padx=16, pady=(0, 14))

        self.start_monitoring()

    def create_stat_card(self, parent, column, icon_file, title):
        styles = {
            "CPU": ("#06152C", "#007FFF", "#00C8FF"),
            "Mémoire (RAM)": ("#1C0633", "#B52CFF", "#ED3CFF"),
            "GPU": ("#031F19", "#00B987", "#00F5A0"),
            "Disque système": ("#21082C", "#D238FF", "#FF57E8"),
        }
        background, border, accent = styles.get(title, (CARD, "#5A22B8", BLUE_BRIGHT))
        card = ctk.CTkFrame(
            parent,
            fg_color=background,
            corner_radius=15,
            border_width=1,
            border_color=border
        )
        card.grid(row=0, column=column, sticky="ew", padx=4)

        stat_body = ctk.CTkFrame(card, fg_color="transparent")
        stat_body.pack(fill="x", padx=15, pady=14)
        ctk.CTkLabel(
            stat_body, image=self.component_icon(icon_file, (76, 76)), text=""
        ).pack(side="left", padx=(0, 13))
        stat_content = ctk.CTkFrame(stat_body, fg_color="transparent")
        stat_content.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            stat_content, text=title, text_color="#F5F0FF",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w")

        value = ctk.CTkLabel(
            stat_content, text="—",
            font=ctk.CTkFont(size=25, weight="bold")
        )
        value.pack(anchor="w", pady=(6, 0))

        bar = ctk.CTkProgressBar(
            stat_content, height=9,
            progress_color=accent,
            fg_color="#25113C"
        )
        bar.pack(fill="x", pady=(10, 7))
        bar.set(0)

        info = ctk.CTkLabel(
            stat_content, text="Chargement...",
            text_color=MUTED,
            font=ctk.CTkFont(size=10),
            wraplength=210,
            justify="left"
        )
        info.pack(anchor="w")

        return {"value": value, "bar": bar, "info": info}

    def create_small_card(self, parent, column, icon_file, title, value):
        styles = {
            "CPU": ("#06152C", "#007FFF"),
            "Barrettes RAM": ("#1C0633", "#B52CFF"),
            "SSD / Disque": ("#1C0633", "#B52CFF"),
            "Température": ("#2B1008", "#FF6616"),
        }
        background, border = styles.get(title, (CARD, "#2E1850"))
        card = ctk.CTkFrame(
            parent,
            fg_color=background,
            corner_radius=14,
            border_width=1,
            border_color=border
        )
        card.grid(row=0, column=column, sticky="ew", padx=4)

        detail_body = ctk.CTkFrame(card, fg_color="transparent")
        detail_body.pack(fill="x", padx=15, pady=13)
        ctk.CTkLabel(
            detail_body, image=self.component_icon(icon_file, (50, 50)), text=""
        ).pack(side="left", padx=(0, 12))
        detail_content = ctk.CTkFrame(detail_body, fg_color="transparent")
        detail_content.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            detail_content, text=title,
            text_color="#F5F0FF", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w")

        value_label = ctk.CTkLabel(
            detail_content, text=value,
            text_color=BLUE_BRIGHT,
            font=ctk.CTkFont(size=12, weight="bold"),
            justify="left"
        )
        value_label.pack(anchor="w", pady=(5, 0))

        return value_label

    # --------------------------------------------------------
    # STATISTIQUES
    # --------------------------------------------------------

    def start_monitoring(self):
        """Lance la récupération matérielle hors du thread graphique."""
        self.stats_queue = queue.Queue()
        self.monitor_running = True

        # Les noms du matériel sont déjà initialisés dans __init__.
        # On ne les récupère pas une seconde fois ici.

        self.monitor_thread = threading.Thread(
            target=self.monitor_worker,
            daemon=True
        )
        self.monitor_thread.start()

        # Le thread Tkinter ne fait que récupérer les résultats déjà calculés.
        self.after(1000, self.apply_stats)

    def monitor_worker(self):
        """Récupère les statistiques sans bloquer l'interface."""
        import time
        while self.monitor_running:
            try:
                cpu = psutil.cpu_percent(interval=1.0)
                memory = psutil.virtual_memory()

                try:
                    disk = psutil.disk_usage("C:\\")
                except Exception:
                    disk = None

                cpu_frequency = get_cpu_frequency()

                # Les températures / GPU utilisent PowerShell ou nvidia-smi,
                # donc ils restent hors du thread principal.
                cpu_temperature = get_cpu_temperature()
                gpu_usage, gpu_temperature = get_gpu_stats()

                self.stats_queue.put({
                    "cpu": cpu,
                    "memory": memory,
                    "disk": disk,
                    "cpu_frequency": cpu_frequency,
                    "cpu_temperature": cpu_temperature,
                    "gpu_usage": gpu_usage,
                    "gpu_temperature": gpu_temperature
                })

            except Exception:
                pass

    def apply_stats(self):
        """Met à jour l'interface sans lancer de commande système."""
        try:
            stats = self.stats_queue.get_nowait()
        except queue.Empty:
            if self.monitor_running:
                self.after(1000, self.apply_stats)
            return

        cpu = stats["cpu"]
        memory = stats["memory"]
        disk = stats["disk"]
        cpu_frequency = stats["cpu_frequency"]
        cpu_temperature = stats["cpu_temperature"]
        gpu_usage = stats["gpu_usage"]
        gpu_temperature = stats["gpu_temperature"]

        # CPU
        self.cpu_card["value"].configure(text=f"{cpu:.0f}%")
        self.cpu_card["bar"].set(max(0, min(1, cpu / 100)))

        cpu_info = self.cpu_name
        if cpu_temperature is not None:
            cpu_info += f"\n?? {temp_text(cpu_temperature)}"

        self.cpu_card["info"].configure(text=cpu_info)

        # RAM
        self.ram_card["value"].configure(
            text=f"{memory.percent:.0f}%"
        )
        self.ram_card["bar"].set(
            max(0, min(1, memory.percent / 100))
        )
        installed_ram = len(self.ram_modules)
        total_slots = self.ram_slot_count or installed_ram
        ram_positions = ", ".join(
            module["position"] for module in self.ram_modules
        ) or "Positions non détectées"
        ram_layout = (
            f"{installed_ram}/{total_slots} barrettes"
            if installed_ram else "N/D"
        )
        self.ram_card["info"].configure(
            text=(
                f"{memory.used / 1024**3:.1f} / "
                f"{memory.total / 1024**3:.1f} Go • {ram_layout}"
            )
        )

        # GPU
        if gpu_usage is None:
            self.gpu_card["value"].configure(text="N/D")
            self.gpu_card["bar"].set(0)
        else:
            self.gpu_card["value"].configure(
                text=f"{gpu_usage:.0f}%"
            )
            self.gpu_card["bar"].set(
                max(0, min(1, gpu_usage / 100))
            )

        self.gpu_card["info"].configure(text=self.gpu_name)

        # Disque
        if disk is not None:
            self.disk_card["value"].configure(
                text=f"{disk.percent:.0f}%"
            )
            self.disk_card["bar"].set(
                max(0, min(1, disk.percent / 100))
            )
            self.disk_card["info"].configure(
                text=(
                    f"{disk.used / 1024**3:.0f} / "
                    f"{disk.total / 1024**3:.0f} Go"
                )
            )

            self.disk_detail_card.configure(
                text=(
                    f"Utilisation en direct : {disk.percent:.0f} %\n"
                    f"{disk.used / 1024**3:.0f} / "
                    f"{disk.total / 1024**3:.0f} Go"
                )
            )

        # Détails CPU
        frequency = (
            f"{cpu_frequency:.2f} GHz"
            if cpu_frequency is not None
            else "N/D"
        )

        cpu_detail = f"Fréquence en direct : {frequency}"

        if cpu_temperature is not None:
            cpu_detail += (
                f"\nTempérature : {temp_text(cpu_temperature)}"
            )
        else:
            cpu_detail += "\nTempérature : capteur non détecté"

        self.cpu_detail_card.configure(
            text=cpu_detail
        )

        # Cette carte remplace le doublon de charge GPU par la configuration RAM.
        self.ram_detail_card.configure(
            text=f"{ram_layout}\n{ram_positions}"
        )

        # Température : CPU + GPU regroupées au même endroit.
        self.motherboard_detail_card.configure(
            text=(
                f"CPU : {temp_text(cpu_temperature)}\n"
                f"GPU : {temp_text(gpu_temperature)}"
            )
        )

        # Système
        self.system_label.configure(
            text=(
                f"{platform.system()} {platform.release()}\n"
                f"{self.cpu_name}\n"
                f"{memory.total / 1024**3:.1f} Go RAM ({ram_layout})\n"
                f"{self.gpu_name}"
            )
        )

        if self.monitor_running:
            self.after(1000, self.apply_stats)

    # --------------------------------------------------------
    # PAGES
    # --------------------------------------------------------

    def simple_page(self, title, description, menu):
        self.clear_content()
        self.active_menu(menu)

        ctk.CTkLabel(
            self.content,
            text=title,
            font=ctk.CTkFont(size=28, weight="bold")
        ).pack(anchor="w", padx=5, pady=(10, 3))

        ctk.CTkLabel(
            self.content,
            text=description,
            text_color=MUTED
        ).pack(anchor="w", padx=5, pady=(0, 20))

        card = ctk.CTkFrame(
            self.content,
            fg_color=CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER
        )
        card.pack(fill="x", pady=5)

        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", padx=20, pady=20)

        ctk.CTkLabel(
            card,
            text="Cette section sera bientôt disponible.",
            text_color=MUTED
        ).pack(anchor="w", padx=20, pady=(0, 20))

    def show_apps(self):
        self.clear_content()
        self.active_menu("Apps")

        header = ctk.CTkFrame(
            self.content,
            fg_color="#110923", corner_radius=18,
            border_width=1, border_color="#5A22B8"
        )
        header.pack(fill="x", pady=(4, 12), padx=2)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        self.add_page_title(left, "apps.png", "Apps")

        ctk.CTkLabel(
            left,
            text="🧰 Outils recommandés pour optimiser et surveiller votre PC.",
            text_color=MUTED
        ).pack(anchor="w", pady=(3, 0))

        self.apps_status = ctk.CTkLabel(
            left,
            text="📦 Vérification des installations...",
            text_color=MUTED,
            font=ctk.CTkFont(size=11)
        )
        self.apps_status.pack(anchor="w", pady=(7, 0))

        self.install_all_button = ctk.CTkButton(
            header,
            text="Tout installer",
            width=155,
            height=42,
            corner_radius=10,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.install_all_apps
        )
        self.install_all_button.pack(side="right", padx=(10, 0))

        self.apps_grid = ctk.CTkFrame(
            self.content,
            fg_color="transparent"
        )
        self.apps_grid.pack(fill="both", expand=True)

        self.apps_grid.grid_columnconfigure(0, weight=1)
        self.apps_grid.grid_columnconfigure(1, weight=1)

        self.app_widgets = {}

        for index, app in enumerate(APP_CATALOG):
            self.create_app_card(
                self.apps_grid,
                index // 2,
                index % 2,
                app
            )

        # Les vérifications Winget sont faites hors du thread Tkinter.
        threading.Thread(
            target=self.refresh_app_states,
            daemon=True
        ).start()

    def create_app_card(self, parent, row, column, app):
        card = ctk.CTkFrame(
            parent,
            fg_color=CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER
        )
        card.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=5,
            pady=5
        )

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            top, image=self.colored_icon(
                APP_ICON_FILES.get(app["name"], "apps.png"), (40, 40)
            ), text=""
        ).pack(side="left")

        name_frame = ctk.CTkFrame(top, fg_color="transparent")
        name_frame.pack(side="left", padx=10, fill="x", expand=True)

        ctk.CTkLabel(
            name_frame,
            text=app["name"],
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            name_frame,
            text=app["category"],
            text_color="#A16BFF",
            font=ctk.CTkFont(size=10, weight="bold")
        ).pack(anchor="w", pady=(2, 0))

        ctk.CTkLabel(
            card,
            text=app["description"],
            text_color="#A9A4B3",
            justify="left",
            anchor="w",
            wraplength=390
        ).pack(fill="x", padx=15, pady=(8, 12))

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=15, pady=(0, 15))

        install_button = ctk.CTkButton(
            bottom,
            text="Installer",
            width=120,
            height=38,
            corner_radius=9,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
            command=lambda a=app: self.install_one_app(a)
        )
        install_button.pack(side="left")

        uninstall_button = ctk.CTkButton(
            bottom, text="Désinstaller", width=120, height=38,
            corner_radius=9, fg_color="#572A3C", hover_color="#74364D",
            command=lambda a=app: self.uninstall_catalog_app(a)
        )

        status = ctk.CTkLabel(
            bottom,
            text="Non installé",
            text_color="#A7A1AF",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        status.pack(side="right")

        self.app_widgets[app["name"]] = {
            "button": install_button,
            "uninstall": uninstall_button,
            "status": status
        }

        if app["package"] == "ISLC_WEB":
            install_button.configure(
                text="?? Ouvrir",
                state="normal",
                fg_color=PURPLE
            )
        elif app["package"] == "GITHUB_DOWNLOAD":
            install_button.configure(
                text="?? Lancer",
                state="normal",
                fg_color=PURPLE
            )
        elif app["package"] == "LOCAL_INSTALLER":
            install_button.configure(
                text="?? Installer",
                state="normal",
                fg_color=PURPLE
            )
        elif app["package"] == "LOCAL_ZIP":
            install_button.configure(
                text="?? Installer",
                state="normal",
                fg_color=PURPLE
            )

    def uninstall_catalog_app(self, app):
        if not messagebox.askyesno(
            "Désinstallation", f"Désinstaller {app['name']} ?"
        ):
            return
        widgets = self.app_widgets.get(app["name"], {})
        if widgets.get("status"):
            widgets["status"].configure(text="Désinstallation...", text_color="#FFB36B")

        def worker():
            try:
                success = self.app_uninstall_or_reinstall(app["package"], "uninstall")
            except Exception:
                success = False
            self.after(0, lambda: self.show_apps() if success else widgets["status"].configure(
                text="Désinstallation impossible", text_color="#FF6B8A"
            ))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_app_states(self):
        states = {}

        for app in APP_CATALOG:
            if app["package"] == "ISLC_WEB":
                states[app["name"]] = True
            elif app["package"] == "GITHUB_DOWNLOAD":
                states[app["name"]] = self.get_local_msi_utility() is not None
            elif app["package"] == "LOCAL_INSTALLER":
                states[app["name"]] = self.find_local_installer(app["installer_name"]) is not None
            elif app["package"] in ("LOCAL_ZIP", "GITHUB_ZIP"):
                states[app["name"]] = self.local_app_installed(app)
            elif app["package"]:
                states[app["name"]] = winget_installed(app["package"])
            else:
                states[app["name"]] = False

        self.after(0, lambda: self.apply_app_states(states))

    def apply_app_states(self, states):
        installed_count = 0

        for app in APP_CATALOG:
            widgets = self.app_widgets.get(app["name"])
            if not widgets:
                continue
            widgets["uninstall"].pack_forget()

            if app["package"] is None:
                widgets["status"].configure(
                    text="Manuel",
                    text_color="#A9A4B3"
                )
                continue

            if app["package"] == "ISLC_WEB":
                widgets["button"].configure(
                    text="Ouvrir", state="normal", fg_color=PURPLE
                )
                widgets["status"].configure(
                    text="Page officielle", text_color="#20E59B"
                )
                continue

            if app["package"] == "GITHUB_DOWNLOAD":
                if states.get(app["name"], False):
                    widgets["status"].configure(
                        text="Disponible",
                        text_color="#20E59B"
                    )
                else:
                    widgets["status"].configure(
                        text="Non disponible",
                        text_color="#A9A4B3"
                    )
                continue

            if app["package"] in ("LOCAL_ZIP", "GITHUB_ZIP"):
                if states.get(app["name"], False):
                    installed_count += 1
                    widgets["button"].configure(
                        text="Lancé",
                        state="normal",
                        fg_color=PURPLE
                    )
                    widgets["status"].configure(
                        text="Prêt",
                        text_color="#20E59B"
                    )
                else:
                    widgets["button"].configure(
                        text="Installer",
                        state="normal",
                        fg_color=PURPLE
                    )
                    widgets["status"].configure(
                        text=("Prêt à télécharger" if app["package"] == "GITHUB_ZIP"
                              else "Fichier local requis"),
                        text_color="#A9A4B3"
                    )
                continue

            if states.get(app["name"], False):
                installed_count += 1
                widgets["button"].pack_forget()
                widgets["uninstall"].pack(side="left")
                widgets["status"].configure(
                    text="Installé",
                    text_color="#20E59B"
                )
            else:
                widgets["button"].pack(side="left")
                widgets["button"].configure(
                    text="Installer",
                    state="normal",
                    fg_color=PURPLE
                )
                widgets["status"].configure(
                    text="Non installé",
                    text_color="#A9A4B3"
                )

        self.apps_status.configure(
            text=f"{installed_count}/{len(APP_CATALOG)} applications sont prêtes ou déjà installées."
        )

    def find_local_zip(self, zip_name):
        """Cherche l'outil local dans le paquet, puis dans le dossier Téléchargements.

        Les versions distribuées sont des exécutables PyInstaller : les fichiers
        ajoutés au paquet sont décompressés dans ``sys._MEIPASS``. On vérifie donc
        à la fois ce dossier, le dossier ``client`` extrait et le dossier source,
        tout en conservant le fallback Téléchargements pour les installations
        lancées depuis Python.
        """
        roots = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.extend([Path(meipass), Path(meipass) / "client"])
        roots.extend([
            Path(__file__).resolve().parent,
            Path.home() / "Downloads",
        ])
        candidates = [root / zip_name for root in roots]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def local_app_install_dir(self, app):
        safe = "".join(
            ch if ch.isalnum() else "_"
            for ch in app["name"]
        ).strip("_")
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PerformancePC" / "Apps" / safe

    def local_app_installed(self, app):
        if app["package"] not in ("LOCAL_ZIP", "GITHUB_ZIP"):
            return False
        install_dir = self.local_app_install_dir(app)
        if app["package"] == "GITHUB_ZIP":
            return any(install_dir.rglob(app["exe_name"])) if install_dir.exists() else False
        exe = install_dir / app["exe_path"].replace("/", os.sep)
        return exe.exists() and exe.is_file()

    @staticmethod
    def _tls_verify_bundle():
        """Retourne le bundle CA embarqué, avec repli sur la vérification native."""
        try:
            import certifi
            bundle = Path(certifi.where())
            if bundle.exists() and bundle.is_file():
                return str(bundle)
        except Exception:
            pass
        return True

    def install_github_release_zip(self, app):
        """Télécharge la dernière release GitHub et retrouve l'exécutable."""
        response = requests.get(
            f"https://api.github.com/repos/{app['repo']}/releases/latest",
            timeout=30, headers={"Accept": "application/vnd.github+json"},
            verify=self._tls_verify_bundle(),
        )
        response.raise_for_status()
        assets = response.json().get("assets", [])
        asset = next((item for item in assets if item.get("name", "").lower().endswith(".zip")), None)
        if asset is None:
            raise RuntimeError("Aucune archive ZIP n'a été trouvée dans la release GitHub.")
        archive = requests.get(
            asset["browser_download_url"],
            timeout=180,
            verify=self._tls_verify_bundle(),
        )
        archive.raise_for_status()
        install_dir = self.local_app_install_dir(app)
        install_dir.mkdir(parents=True, exist_ok=True)
        zip_path = install_dir / "release.zip"
        zip_path.write_bytes(archive.content)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(install_dir)
        exe = next(iter(install_dir.rglob(app["exe_name"])), None)
        if exe is None:
            raise FileNotFoundError(f"{app['exe_name']} est absent de l'archive téléchargée.")
        return exe

    def install_local_zip(self, app):
        """Extrait un outil fourni par l'utilisateur puis retourne son EXE."""
        zip_path = self.find_local_zip(app["zip_name"])
        if zip_path is None:
            raise FileNotFoundError(
                f"{app['zip_name']} introuvable. Mets le ZIP à côté de main.py ou dans Téléchargements."
            )

        install_dir = self.local_app_install_dir(app)
        install_dir.mkdir(parents=True, exist_ok=True)

        # On extrait uniquement si l'EXE cible n'existe pas encore.
        target = install_dir / app["exe_path"].replace("/", os.sep)
        if not target.exists():
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(install_dir)

        if not target.exists():
            raise FileNotFoundError(
                f"Fichier {app['exe_path']} introuvable dans {app['zip_name']}."
            )

        return target

    def launch_exe_admin(self, exe_path):
        """Demande l'élévation UAC puis lance un EXE avec les droits administrateur."""
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            str(exe_path),
            None,
            str(Path(exe_path).parent),
            1
        )
        if result <= 32:
            raise RuntimeError(f"Windows a refusé le lancement administrateur (code {result}).")
        return True

    def find_local_installer(self, installer_name):
        """Trouve ISLC localement. Aucun téléchargement si le fichier existe déjà."""
        base = Path(__file__).resolve().parent
        home = Path.home()
        candidates = [
            base / "ISLC" / "Intelligent standby list cleaner ISLC.exe",
            base / "Intelligent standby list cleaner ISLC.exe",
            base / "ISLC" / "ISLC.exe",
            base / "ISLC" / "ISLC v1.0.4.6.exe",
            base / "ISLC_v1.0.3.4.exe",
            home / "Downloads" / "Intelligent standby list cleaner ISLC.exe",
            home / "Downloads" / "ISLC v1.0.4.6.exe",
        ]
        # Accepte aussi un EXE ISLC présent dans un sous-dossier.
        for root in (base, home / "Downloads"):
            try:
                if root.exists():
                    candidates.extend(root.rglob("Intelligent standby list cleaner ISLC.exe"))
            except Exception:
                pass
        seen=set()
        for candidate in candidates:
            candidate=Path(candidate)
            key=str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 100000:
                return candidate
        return None

    def download_islc_official(self):
        """Télécharge ISLC 1.0.4.6 depuis l'URL officielle Wagnardsoft.

        Plusieurs méthodes sont essayées afin d'éviter les échecs HTTP 403 de certains
        environnements Python. Le fichier est contrôlé comme un PE Windows et par SHA-256.
        """
        base = Path(__file__).resolve().parent
        dest_dir = base / "ISLC"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "ISLC v1.0.4.6.exe"
        url = "https://www.wagnardsoft.com/ISLC/ISLC%20v1.0.4.6.exe"
        expected = "606DCBA965AF417D97486B125723BBC5CCE92F830C7791DEF06B0C542A10DF50"

        if dest.exists() and dest.stat().st_size > 100000:
            try:
                if hashlib.sha256(dest.read_bytes()).hexdigest().upper() == expected:
                    return dest
            except Exception:
                pass

        errors=[]
        # 1) curl.exe de Windows : gère mieux certains serveurs que urllib.
        try:
            import subprocess
            r=subprocess.run(
                ["curl.exe","-L","--fail","--retry","3","-A","Mozilla/5.0",
                 "-o",str(dest),url], capture_output=True, text=True, timeout=180
            )
            if r.returncode == 0 and dest.exists() and dest.stat().st_size > 100000:
                data=dest.read_bytes()
                if data[:2] == b"MZ":
                    digest=hashlib.sha256(data).hexdigest().upper()
                    if digest == expected:
                        return dest
                    errors.append(f"SHA-256 inattendu: {digest}")
                else:
                    errors.append("Le serveur n'a pas renvoyé un EXE Windows.")
            else:
                errors.append((r.stderr or "curl a échoué").strip())
        except Exception as exc:
            errors.append(f"curl: {exc}")

        # 2) urllib avec plusieurs User-Agent.
        try:
            from urllib.request import Request, urlopen
            for ua in ("Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                       "PerformancePC/1.0", "curl/8.0"):
                try:
                    req=Request(url, headers={"User-Agent":ua, "Accept":"*/*"})
                    with urlopen(req, timeout=120) as response:
                        data=response.read()
                    if data[:2] != b"MZ":
                        errors.append("Réponse HTTP non exécutable.")
                        continue
                    digest=hashlib.sha256(data).hexdigest().upper()
                    if digest != expected:
                        errors.append(f"SHA-256 inattendu: {digest}")
                        continue
                    dest.write_bytes(data)
                    return dest
                except Exception as exc:
                    errors.append(f"urllib: {exc}")
        except Exception as exc:
            errors.append(f"urllib indisponible: {exc}")

        raise RuntimeError(
            "Impossible de récupérer ISLC depuis le serveur officiel Wagnardsoft.\n\n"
            "Tu peux aussi placer manuellement l'EXE dans :\n"
            f"{dest}\n\n" + "\n".join(e for e in errors if e)[:1800]
        )

    def launch_local_installer_admin(self, installer_path):
        """Lance un EXE local avec UAC. ISLC est lancé depuis son propre dossier."""
        installer_path = Path(installer_path).resolve()
        if not installer_path.exists():
            raise FileNotFoundError(f"EXE introuvable : {installer_path}")

        is_islc = ("intelligent standby list cleaner" in installer_path.name.lower()
                   or installer_path.name.lower().startswith("islc"))
        args = "-minimized" if is_islc else None

        # Le .Config doit être à côté de l'EXE.
        if is_islc:
            config = installer_path.with_name("Intelligent standby list cleaner ISLC.exe.Config")
            alt_config = installer_path.with_suffix(installer_path.suffix + ".Config")
            if not config.exists() and alt_config.exists():
                config = alt_config

        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(installer_path), args,
            str(installer_path.parent), 1
        )
        if result <= 32:
            raise RuntimeError(f"Windows a refusé le lancement d'ISLC (code {result}).")
        return True

    def get_local_msi_utility(self):
        """Cherche MSI Utility v3.exe à côté de main.py."""
        candidates = [
            Path(__file__).resolve().parent / "Msi Utility v3.exe",
            Path.home() / "Downloads" / "Msi Utility v3.exe",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def download_msi_utility(self, destination):
        """Télécharge l'EXE MSI Utility v3 depuis le dépôt GitHub."""
        req = Request(
            "https://github.com/Sathango/Msi-Utility-v3/raw/main/Msi%20Utility%20v3.exe?download=1",
            headers={"User-Agent": "PerformancePC/1.0"}
        )

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        # On retélécharge toujours pour éviter de réutiliser un fichier incomplet.
        with urlopen(req, timeout=60) as response:
            data = response.read()

        # Un vrai EXE Windows commence par MZ.
        if len(data) < 1024 or data[:2] != b"MZ":
            raise RuntimeError("Le fichier téléchargé n'est pas un EXE Windows valide.")

        destination.write_bytes(data)
        return destination

    def launch_msi_utility_admin(self, exe_path):
        """Lance MSI Utility v3 avec la demande UAC Windows."""
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                str(exe_path),
                None,
                None,
                1
            )
            if result <= 32:
                raise RuntimeError(f"Windows ShellExecute a renvoyé le code {result}.")
            return True
        except Exception as exc:
            raise RuntimeError(f"Lancement administrateur impossible : {exc}") from exc

    def open_islc_page(self):
        """Ouvre directement la page officielle de téléchargement ISLC."""
        url = "https://www.wagnardsoft.com/forums/viewtopic.php?t=1256"
        try:
            webbrowser.open_new_tab(url)
            return True
        except Exception as exc:
            raise RuntimeError(f"Impossible d'ouvrir la page officielle ISLC : {exc}") from exc

    def install_one_app(self, app):
        if not app["package"]:
            return

        widgets = self.app_widgets[app["name"]]
        widgets["button"].configure(
            text="En cours...",
            state="disabled",
            fg_color="#282535"
        )
        widgets["status"].configure(
            text="? Préparation...",
            text_color="#A16BFF"
        )

        def worker():
            success = False
            error_text = ""

            try:
                if app["package"] == "ISLC_WEB":
                    success = self.open_islc_page()

                elif app["package"] == "LOCAL_INSTALLER":
                    self.after(0, lambda: widgets["status"].configure(
                        text="? Préparation de l'installateur...",
                        text_color="#A16BFF"
                    ))
                    installer = self.find_local_installer(app["installer_name"])
                    if installer is None and app["name"] == "ISLC":
                        self.after(0, lambda: widgets["status"].configure(
                            text="? Téléchargement officiel ISLC...", text_color="#A16BFF"))
                        installer = self.download_islc_official()
                    if installer is None:
                        raise FileNotFoundError(f"{app['installer_name']} introuvable.")
                    success = self.launch_local_installer_admin(installer)

                elif app["package"] == "LOCAL_ZIP":
                    self.after(
                        0,
                        lambda: widgets["status"].configure(
                            text="? Extraction...",
                            text_color="#A16BFF"
                        )
                    )
                    exe = self.install_local_zip(app)

                    self.after(
                        0,
                        lambda: widgets["status"].configure(
                            text="? Demande administrateur...",
                            text_color="#A16BFF"
                        )
                    )
                    success = self.launch_exe_admin(exe)

                elif app["package"] == "GITHUB_ZIP":
                    self.after(0, lambda: widgets["status"].configure(
                        text="Téléchargement de la release GitHub...", text_color="#A16BFF"))
                    exe = self.install_github_release_zip(app)
                    success = self.launch_exe_admin(exe)

                elif app["package"] == "GITHUB_DOWNLOAD":
                    destination = self.get_local_msi_utility()
                    if destination is None:
                        destination = Path.home() / "Downloads" / "MSI_util_v3.exe"
                        self.download_msi_utility(destination)
                    success = self.launch_msi_utility_admin(destination)

                else:
                    success = install_winget_package(app["package"])

            except Exception as exc:
                error_text = str(exc)

            def finish():
                if success:
                    widgets["button"].configure(
                        text="?? Ouvrir" if app["package"] == "ISLC_WEB"
                        else ("Relancer" if app["package"] == "LOCAL_INSTALLER"
                        else ("Lancé" if app["package"] in ("LOCAL_ZIP", "GITHUB_DOWNLOAD") else "Installé")),
                        state="normal" if app["package"] in ("ISLC_WEB", "LOCAL_INSTALLER", "LOCAL_ZIP", "GITHUB_DOWNLOAD") else "disabled",
                        fg_color=PURPLE if app["package"] in ("ISLC_WEB", "LOCAL_INSTALLER", "LOCAL_ZIP", "GITHUB_DOWNLOAD") else "#282535"
                    )
                    widgets["status"].configure(
                        text="? Page officielle ouverte ?" if app["package"] == "ISLC_WEB"
                        else ("? Installateur lancé ?" if app["package"] == "LOCAL_INSTALLER"
                        else ("Prêt / lancé" if app["package"] == "LOCAL_ZIP"
                        else ("Lancé avec les droits admin" if app["package"] == "GITHUB_DOWNLOAD" else "Installé"))),
                        text_color="#20E59B"
                    )
                else:
                    widgets["button"].configure(
                        text="Réessayer",
                        state="normal",
                        fg_color=PURPLE
                    )
                    widgets["status"].configure(
                        text="? " + (error_text[:55] if error_text else "Échec"),
                        text_color="#FF7070"
                    )

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def install_all_apps(self):
        self.install_all_button.configure(
            text="Installation...",
            state="disabled"
        )
        self.apps_status.configure(
            text="Installation des applications en cours..."
        )

        def worker():
            for app in APP_CATALOG:
                if not app["package"]:
                    continue

                widgets = self.app_widgets[app["name"]]

                self.after(
                    0,
                    lambda name=app["name"]: self.app_widgets[name]["status"].configure(
                        text="? En cours...",
                        text_color="#A16BFF"
                    )
                )

                try:
                    if app["package"] == "ISLC_WEB":
                        self.open_islc_page()
                        self.after(0, lambda name=app["name"]: (
                            self.app_widgets[name]["button"].configure(text="?? Ouvrir", state="normal", fg_color=PURPLE),
                            self.app_widgets[name]["status"].configure(text="? Page officielle ouverte ?", text_color="#20E59B")
                        ))
                        continue

                    if app["package"] == "LOCAL_INSTALLER":
                        installer = self.find_local_installer(app["installer_name"])
                        if installer is None and app["name"] == "ISLC":
                            installer = self.download_islc_official()
                        if installer is None:
                            raise FileNotFoundError(f"{app['installer_name']} introuvable.")
                        self.launch_local_installer_admin(installer)
                        self.after(0, lambda name=app["name"]: (
                            self.app_widgets[name]["button"].configure(
                                text="Relancer", state="normal", fg_color=PURPLE
                            ),
                            self.app_widgets[name]["status"].configure(
                                text="? Installateur lancé ?", text_color="#20E59B"
                            )
                        ))
                        continue

                    if app["package"] == "LOCAL_ZIP":
                        exe = self.install_local_zip(app)
                        self.after(
                            0,
                            lambda name=app["name"]: self.app_widgets[name]["status"].configure(
                                text="? Demande administrateur...",
                                text_color="#A16BFF"
                            )
                        )
                        self.launch_exe_admin(exe)

                        self.after(
                            0,
                            lambda name=app["name"]: (
                                self.app_widgets[name]["button"].configure(
                                    text="Lancé",
                                    state="normal",
                                    fg_color=PURPLE
                                ),
                                self.app_widgets[name]["status"].configure(
                                    text="Prêt / lancé",
                                    text_color="#20E59B"
                                )
                            )
                        )
                        continue

                    if app["package"] == "GITHUB_DOWNLOAD":
                        destination = self.get_local_msi_utility()
                        if destination is None:
                            destination = Path.home() / "Downloads" / "MSI_util_v3.exe"
                            self.download_msi_utility(destination)
                        self.launch_msi_utility_admin(destination)
                        self.after(
                            0,
                            lambda name=app["name"]: (
                                self.app_widgets[name]["button"].configure(
                                    text="Lancé",
                                    state="normal",
                                    fg_color=PURPLE
                                ),
                                self.app_widgets[name]["status"].configure(
                                    text="Lancé avec les droits admin",
                                    text_color="#20E59B"
                                )
                            )
                        )
                        continue

                    if winget_installed(app["package"]):
                        self.after(
                            0,
                            lambda name=app["name"]: (
                                self.app_widgets[name]["button"].configure(
                                    text="Installé",
                                    state="disabled",
                                    fg_color="#282535"
                                ),
                                self.app_widgets[name]["status"].configure(
                                    text="? Déjà installé ?",
                                    text_color="#20E59B"
                                )
                            )
                        )
                        continue

                    success = install_winget_package(app["package"])

                    if success:
                        self.after(
                            0,
                            lambda name=app["name"]: (
                                self.app_widgets[name]["button"].configure(
                                    text="Installé",
                                    state="disabled",
                                    fg_color="#282535"
                                ),
                                self.app_widgets[name]["status"].configure(
                                    text="? Installé ?",
                                    text_color="#20E59B"
                                )
                            )
                        )
                    else:
                        raise RuntimeError("Winget n'a pas réussi l'installation.")

                except Exception as exc:
                    error = str(exc)
                    self.after(
                        0,
                        lambda name=app["name"], msg=error: self.app_widgets[name]["status"].configure(
                            text="? " + (msg[:55] if msg else "Échec"),
                            text_color="#FF7070"
                        )
                    )

            self.after(
                0,
                lambda: (
                    self.install_all_button.configure(
                        text="? Tout installer",
                        state="normal"
                    ),
                    self.apps_status.configure(
                        text="Installation / préparation terminée."
                    )
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def run_admin_powershell(self, script, on_done=None):
        """Exécute le script en arrière-plan sans afficher de fenêtre PowerShell."""
        import base64
        import subprocess
        import tempfile

        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")

        # Processus PowerShell caché. L'UAC peut toujours apparaître si nécessaire,
        # mais aucune console PowerShell ne sera affichée pendant l'opération.
        command = (
            f"$s=[Text.Encoding]::Unicode.GetString("
            f"[Convert]::FromBase64String('{encoded}')); "
            f"Invoke-Expression $s"
        )

        def worker():
            success = False
            try:
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 0

                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy", "Bypass",
                        "-WindowStyle", "Hidden",
                        "-Command", command
                    ],
                    startupinfo=startup,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                success = result.returncode == 0
            except Exception:
                success = False

            if on_done:
                self.after(0, lambda: on_done(success))

            return success

        threading.Thread(target=worker, daemon=True).start()
        return True


    def open_windows_settings(self, uri):
        try:
            os.startfile(uri)
        except Exception as exc:
            messagebox.showerror("PerformancePC", f"Impossible d'ouvrir les paramètres : {exc}")

    def optimize_ssd(self):
        self.show_optimization_loading("Optimisation de tous les disques...")

        script = r'''
$ErrorActionPreference = 'Continue'
$results = @()

$volumes = Get-Volume | Where-Object {
    $_.DriveLetter -and $_.DriveType -eq 'Fixed'
}

foreach ($volume in $volumes) {
    $letter = [string]$volume.DriveLetter
    try {
        # Windows choisit l'opération adaptée au support :
        # ReTrim pour SSD, optimisation/défragmentation pour HDD.
        Optimize-Volume -DriveLetter $letter -Verbose -ErrorAction Stop | Out-Null
        $results += "$letter`: OK"
    }
    catch {
        $results += "$letter`: ECHEC"
    }
}

$results -join "`n"
'''
        def done(success):
            self.hide_optimization_loading()
            if success:
                messagebox.showinfo(
                    "PerformancePC",
                    "Tous les disques fixes détectés ont été optimisés."
                )
            else:
                messagebox.showerror(
                    "PerformancePC",
                    "L'optimisation des disques a échoué."
                )
        self.run_admin_powershell(script, done)

    def create_restore_point(self):
        """Crée directement un point de restauration nommé AtomeOpti Restore."""
        self.show_optimization_loading("Création du point de restauration...")
        script = r"""
$ErrorActionPreference = 'Stop'
Enable-ComputerRestore -Drive "$env:SystemDrive\"
Checkpoint-Computer -Description "AtomeOpti Restore" -RestorePointType "MODIFY_SETTINGS"
"""

        def done(success):
            self.hide_optimization_loading()
            if success:
                messagebox.showinfo(
                    "PerformancePC",
                    "Le point de restauration « AtomeOpti Restore » a été créé."
                )
            else:
                messagebox.showerror(
                    "PerformancePC",
                    "Impossible de créer le point de restauration. Vérifie que la Protection du système est disponible sur Windows."
                )

        self.run_admin_powershell(script, done)


    def optimize_game_settings(self):
        """Active les optimisations graphiques et désactive Game Bar/captures sans ouvrir de page."""
        script = r"""
$gameBar = 'HKCU:\SOFTWARE\Microsoft\GameBar'
$gameDvr = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR'
$gameConfig = 'HKCU:\SYSTEM\GameConfigStore'
$gpu = 'HKCU:\SOFTWARE\Microsoft\DirectX\UserGpuPreferences'

New-Item -Path $gameBar -Force | Out-Null
New-Item -Path $gameDvr -Force | Out-Null
New-Item -Path $gameConfig -Force | Out-Null
New-Item -Path $gpu -Force | Out-Null

# MODE JEU WINDOWS = ON
New-ItemProperty -Path $gameBar -Name AutoGameModeEnabled -PropertyType DWord -Value 1 -Force | Out-Null
New-ItemProperty -Path $gameBar -Name GameModeEnabled -PropertyType DWord -Value 1 -Force | Out-Null

# Game Bar / Captures OFF
New-ItemProperty -Path $gameDvr -Name AppCaptureEnabled -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $gameConfig -Name GameDVR_Enabled -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $gameBar -Name ShowStartupPanel -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $gameBar -Name UseNexusForGameBarEnabled -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $gameBar -Name AllowGameBar -PropertyType DWord -Value 0 -Force | Out-Null

# Optimisations pour les jeux fenêtrés ON
$current = (Get-ItemProperty -Path $gpu -Name DirectXUserGlobalSettings -ErrorAction SilentlyContinue).DirectXUserGlobalSettings
if ([string]::IsNullOrWhiteSpace($current)) {
    $current = 'SwapEffectUpgradeEnable=1;'
} elseif ($current -notmatch '(^|;)SwapEffectUpgradeEnable=') {
    $current = $current.TrimEnd(';') + ';SwapEffectUpgradeEnable=1;'
} else {
    $current = [regex]::Replace($current, 'SwapEffectUpgradeEnable=[01]', 'SwapEffectUpgradeEnable=1')
}
New-ItemProperty -Path $gpu -Name DirectXUserGlobalSettings -PropertyType String -Value $current -Force | Out-Null
"""
        if self.run_admin_powershell(script):
            messagebox.showinfo("PerformancePC", "Game Bar/captures désactivés et optimisations pour les jeux fenêtrés activées.")

    def enable_game_mode(self):
        script = r'''
$gameBar = 'HKCU:\SOFTWARE\Microsoft\GameBar'
New-Item -Path $gameBar -Force | Out-Null
New-ItemProperty -Path $gameBar -Name AutoGameModeEnabled -PropertyType DWord -Value 1 -Force | Out-Null
New-ItemProperty -Path $gameBar -Name GameModeEnabled -PropertyType DWord -Value 1 -Force | Out-Null
'''
        self.show_optimization_loading("Activation du Mode Jeu Windows...")
        def done(success):
            self.hide_optimization_loading()
            if success:
                messagebox.showinfo(
                    "PerformancePC",
                    "Mode Jeu Windows activé.\n\n"
                    "Paramètres ? Jeux ? Mode Jeu ? Activé"
                )
            else:
                messagebox.showerror("PerformancePC", "Impossible d'activer le Mode Jeu Windows.")
        self.run_admin_powershell(script, done)

    def disable_memory_integrity(self):
        if not messagebox.askyesno("Intégrité de la mémoire", "Cette optimisation réduit la sécurité de Windows.\n\nDésactiver l'intégrité de la mémoire peut améliorer les performances, mais diminue la protection du système.\n\nContinuer ?"):
            return
        script = r"""
$path = 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity'
New-Item -Path $path -Force | Out-Null
New-ItemProperty -Path $path -Name Enabled -PropertyType DWord -Value 0 -Force | Out-Null
"""
        if self.run_admin_powershell(script):
            messagebox.showinfo("PerformancePC", "Réglage appliqué. Redémarre Windows pour que le changement soit pleinement pris en compte.")

    def optimize_notifications(self):
        """Désactive les notifications et active Ne pas déranger, sans ouvrir les paramètres."""
        script = r"""
# Notifications uniquement (Ne pas déranger reste inchangé)
$push = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\PushNotifications'
$notif = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings'

New-Item -Path $push -Force | Out-Null
New-Item -Path $notif -Force | Out-Null

New-ItemProperty -Path $push -Name ToastEnabled -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $notif -Name NOC_GLOBAL_SETTING_DND -PropertyType DWord -Value 1 -Force | Out-Null
New-ItemProperty -Path $notif -Name NOC_GLOBAL_SETTING_DND_ENABLED -PropertyType DWord -Value 1 -Force | Out-Null
New-ItemProperty -Path $notif -Name NOC_GLOBAL_SETTING_TOASTS_ENABLED -PropertyType DWord -Value 0 -Force | Out-Null

# Recharge Explorer pour prendre en compte les réglages utilisateur.
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Process explorer.exe
"""
        if self.run_admin_powershell(script):
            messagebox.showinfo("PerformancePC", "Notifications désactivées.")

    def show_optimization_loading(self, text="Application des réglages..."):
        """Affiche un chargement dans l'application sans ouvrir PowerShell."""
        if hasattr(self, "_loading_overlay") and self._loading_overlay is not None:
            try:
                self._loading_label.configure(text=text)
                return
            except Exception:
                pass

        try:
            self._loading_overlay = ctk.CTkFrame(
                self,
                fg_color="#17131F",
                corner_radius=18
            )
            self._loading_overlay.place(
                relx=0.5, rely=0.5,
                anchor="center",
                relwidth=0.42,
                relheight=0.20
            )

            self._loading_label = ctk.CTkLabel(
                self._loading_overlay,
                text="? " + text,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="white"
            )
            self._loading_label.pack(expand=True)

            self.update_idletasks()
        except Exception:
            self._loading_overlay = None

    def hide_optimization_loading(self):
        try:
            if getattr(self, "_loading_overlay", None) is not None:
                self._loading_overlay.destroy()
                self._loading_overlay = None
        except Exception:
            self._loading_overlay = None

    def optimize_mouse_keyboard(self):
        """Applique souris/clavier + gestion d'alimentation USB automatiquement."""
        script = r"""
# ============================================================
# SOURIS : "Améliorer la précision du pointeur" = OFF
# ============================================================
$mouse = 'HKCU:\Control Panel\Mouse'
Set-ItemProperty -Path $mouse -Name MouseSpeed -Value '0'
Set-ItemProperty -Path $mouse -Name MouseThreshold1 -Value '0'
Set-ItemProperty -Path $mouse -Name MouseThreshold2 -Value '0'

# Appliquer immédiatement les paramètres souris.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class MouseSettings {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SystemParametersInfo(
        uint uiAction, uint uiParam, int[] pvParam, uint fWinIni);
}
'@
[int[]]$mouseParams = @(0,0,0)
[MouseSettings]::SystemParametersInfo(0x0004, 0, $mouseParams, 0x03) | Out-Null

# ============================================================
# CLAVIER : délai court + répétition rapide
# ============================================================
$keyboard = 'HKCU:\Control Panel\Keyboard'
Set-ItemProperty -Path $keyboard -Name KeyboardDelay -Value '0'
Set-ItemProperty -Path $keyboard -Name KeyboardSpeed -Value '31'

# ============================================================
# POWER MANAGEMENT :
# utilise la classe Windows MSPower_DeviceEnable.
#
# C'est cette classe qui correspond directement à la gestion
# d'alimentation affichée dans l'onglet Power Management de
# certains périphériques du Gestionnaire de périphériques.
# ============================================================
try {
    $powerDevices = Get-CimInstance -Namespace root/WMI `
        -ClassName MSPower_DeviceEnable -ErrorAction Stop

    $count = 0

    foreach ($p in $powerDevices) {
        $instance = [string]$p.InstanceName

        # USB controllers / hubs / USB devices + HID souris/claviers.
        if (
            $instance -match 'USB' -or
            $instance -match 'HID' -or
            $instance -match 'MOUSE' -or
            $instance -match 'KEYBOARD'
        ) {
            try {
                Set-CimInstance -InputObject $p -Property @{ Enable = $false } `
                    -ErrorAction Stop | Out-Null
                $count++
            } catch {}
        }
    }
} catch {}

# ============================================================
# Complément : Enhanced Power Management pour les périphériques
# USB qui exposent cette valeur dans Device Parameters.
# ============================================================
try {
    $usbDevices = Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object {
            $_.PNPDeviceID -and (
                $_.PNPClass -eq 'USB' -or
                $_.PNPClass -eq 'Mouse' -or
                $_.PNPClass -eq 'Keyboard' -or
                $_.Service -match 'USB|HID|mouhid|kbdhid'
            )
        }

    foreach ($device in $usbDevices) {
        $deviceId = [string]$device.PNPDeviceID
        $regPath = "HKLM:\SYSTEM\CurrentControlSet\Enum\$deviceId\Device Parameters"

        if (Test-Path $regPath) {
            try {
                New-ItemProperty -Path $regPath `
                    -Name EnhancedPowerManagementEnabled `
                    -PropertyType DWord -Value 0 -Force `
                    -ErrorAction Stop | Out-Null
            } catch {}
        }
    }
} catch {}

# ============================================================
# "Autoriser ce périphérique à sortir l'ordinateur du mode veille"
# OFF pour tous les périphériques USB/HID actuellement armés.
# ============================================================
try {
    $wakeDevices = powercfg /devicequery wake_armed 2>$null

    foreach ($name in $wakeDevices) {
        if (
            $name -match 'USB' -or
            $name -match 'HID' -or
            $name -match 'Mouse' -or
            $name -match 'Keyboard' -or
            $name -match 'Souris' -or
            $name -match 'Clavier'
        ) {
            powercfg /devicedisablewake "$name" 2>$null | Out-Null
        }
    }
} catch {}

# Recharge les paramètres utilisateur.
rundll32.exe user32.dll,UpdatePerUserSystemParameters
"""

        self.show_optimization_loading("Application des réglages...")

        def done(success):
            self.hide_optimization_loading()
            if success:
                messagebox.showinfo(
                    "PerformancePC",
                    "Souris, clavier et gestion d'alimentation USB appliqués."
                )
            else:
                messagebox.showerror(
                    "PerformancePC",
                    "Impossible d'appliquer certains réglages."
                )

        self.run_admin_powershell(script, done)

    def open_device_power_management(self):
        # Compatibilité avec l'ancien bouton : tout est maintenant automatique.
        self.optimize_mouse_keyboard()


    def optimize_all_windows(self):

        if not self.premium_active:
            messagebox.showwarning(
                "AtomeOpti",
                "?? Cette optimisation complète nécessite une activation."
            )
            return
        if not messagebox.askyesno(
            "Optimiser Windows",
            "Appliquer automatiquement les optimisations Windows ?\n\n"
            "• SSD C: / ReTrim\n"
            "• Priorité jeux / Multimedia SystemProfile\n"
            "• Effets visuels performance\n"
            "• Mode Jeu Windows\n"
            "• Game Bar / captures\n"
            "• Télémétrie facultative\n"
            "• Notifications + Ne pas déranger\n"
            "• Souris + clavier\n"
            "• Point de restauration AtomeOpti Restore\n\n"
            "L'intégrité de la mémoire reste séparée car elle réduit la sécurité."
        ):
            return

        self.show_optimization_loading("Optimisation de Windows...")

        script = r"""
$ErrorActionPreference = 'SilentlyContinue'

# ============================================================
# POINT DE RESTAURATION
# ============================================================
try {
    Enable-ComputerRestore -Drive "$env:SystemDrive\" | Out-Null
    Checkpoint-Computer -Description "AtomeOpti Restore" `
        -RestorePointType "MODIFY_SETTINGS" | Out-Null
} catch {}

# ============================================================
# SSD C:
# ============================================================
try {
    Optimize-Volume -DriveLetter C -ReTrim -ErrorAction Stop | Out-Null
} catch {}

# ============================================================
# PRIORITÉ JEUX / MULTIMEDIA SYSTEMPROFILE
# ============================================================
$systemProfile = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile'
$gamesTask = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games'

New-Item -Path $systemProfile -Force | Out-Null
New-Item -Path $gamesTask -Force | Out-Null

# System responsiveness = 0
New-ItemProperty -Path $systemProfile -Name SystemResponsiveness `
    -PropertyType DWord -Value 0 -Force | Out-Null

# Games = High
New-ItemProperty -Path $gamesTask -Name "Scheduling Category" `
    -PropertyType String -Value "High" -Force | Out-Null

# ============================================================
# EFFETS VISUELS : meilleur réglage performance
# ============================================================
$visual = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects'
New-Item -Path $visual -Force | Out-Null
New-ItemProperty -Path $visual -Name VisualFXSetting `
    -PropertyType DWord -Value 2 -Force | Out-Null

# Personnalisation équivalente : désactiver les animations/transparence
$advanced = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced'
New-Item -Path $advanced -Force | Out-Null
New-ItemProperty -Path $advanced -Name TaskbarAnimations -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $advanced -Name ListviewAlphaSelect -PropertyType DWord -Value 0 -Force | Out-Null

# ============================================================
# MODE JEU WINDOWS = ON
# ============================================================
$gameMode = 'HKCU:\Software\Microsoft\GameBar'
New-Item -Path $gameMode -Force | Out-Null
New-ItemProperty -Path $gameMode -Name AutoGameModeEnabled `
    -PropertyType DWord -Value 1 -Force | Out-Null

$gameConfig = 'HKCU:\SYSTEM\GameConfigStore'
New-Item -Path $gameConfig -Force | Out-Null
New-ItemProperty -Path $gameConfig -Name GameDVR_Enabled `
    -PropertyType DWord -Value 0 -Force | Out-Null

# ============================================================
# GAME BAR / CAPTURES = OFF
# ============================================================
$gameDvr = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR'
New-Item -Path $gameDvr -Force | Out-Null
New-ItemProperty -Path $gameDvr -Name AppCaptureEnabled `
    -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $gameMode -Name ShowStartupPanel `
    -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $gameMode -Name UseNexusForGameBarEnabled `
    -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $gameMode -Name AllowGameBar `
    -PropertyType DWord -Value 0 -Force | Out-Null

# ============================================================
# TELEMETRIE : diagnostics facultatifs OFF
# ============================================================
$diag = 'HKCU:\Software\Microsoft\Siuf\Rules'
New-Item -Path $diag -Force | Out-Null
New-ItemProperty -Path $diag -Name NumberOfSIUFInPeriod `
    -PropertyType DWord -Value 0 -Force | Out-Null

# Policy système si disponible
$policy = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection'
New-Item -Path $policy -Force | Out-Null
New-ItemProperty -Path $policy -Name AllowTelemetry `
    -PropertyType DWord -Value 0 -Force | Out-Null

# ============================================================
# NOTIFICATIONS + NE PAS DERANGER
# ============================================================
$push = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\PushNotifications'
$notif = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings'
$focus = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\FocusAssist'

New-Item -Path $push -Force | Out-Null
New-Item -Path $notif -Force | Out-Null
New-Item -Path $focus -Force | Out-Null

New-ItemProperty -Path $push -Name ToastEnabled `
    -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $focus -Name QuietHoursActive `
    -PropertyType DWord -Value 1 -Force | Out-Null
New-ItemProperty -Path $focus -Name QuietHoursEnabled `
    -PropertyType DWord -Value 1 -Force | Out-Null
New-ItemProperty -Path $notif -Name NOC_GLOBAL_SETTING_DND `
    -PropertyType DWord -Value 1 -Force | Out-Null

# ============================================================
# SOURIS + CLAVIER
# ============================================================
$mouse = 'HKCU:\Control Panel\Mouse'
Set-ItemProperty -Path $mouse -Name MouseSpeed -Value '0'
Set-ItemProperty -Path $mouse -Name MouseThreshold1 -Value '0'
Set-ItemProperty -Path $mouse -Name MouseThreshold2 -Value '0'

$keyboard = 'HKCU:\Control Panel\Keyboard'
Set-ItemProperty -Path $keyboard -Name KeyboardDelay -Value '0'
Set-ItemProperty -Path $keyboard -Name KeyboardSpeed -Value '31'

rundll32.exe user32.dll,UpdatePerUserSystemParameters
"""
        def done(success):
            self.hide_optimization_loading()
            if success:
                messagebox.showinfo(
                    "PerformancePC",
                    "Optimisations Windows appliquées.\n\n"
                    "? SSD / ReTrim\n"
                    "? Priorité jeux\n"
                    "? Effets visuels performance\n"
                    "? Mode Jeu\n"
                    "? Game Bar / captures\n"
                    "? Télémétrie\n"
                    "? Notifications / Ne pas déranger\n"
                    "? Souris / clavier\n"
                    "? Point de restauration"
                )
            else:
                messagebox.showerror("PerformancePC", "Certaines optimisations Windows n'ont pas pu être appliquées.")
        self.run_admin_powershell(script, done)

    # --------------------------------------------------------
    # LICENCE PREMIUM / GENKEY
    # --------------------------------------------------------

    def show_premium_activation(self):
        """Affiche l'écran d'activation Premium et vérifie la clé via le serveur."""
        self.clear_content()
        self.active_menu("")

        hero = ctk.CTkFrame(
            self.content,
            fg_color="#0A0615",
            corner_radius=20,
            border_width=1,
            border_color="#5A22B8"
        )
        hero.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            hero,
            text="?? ACTIVATION",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="white"
        ).pack(anchor="w", padx=24, pady=(24, 6))

        ctk.CTkLabel(
            hero,
            text="Entre ta clé d'activation.",
            text_color=MUTED,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=24, pady=(0, 24))

        card = ctk.CTkFrame(
            self.content,
            fg_color=CARD,
            corner_radius=18,
            border_width=1,
            border_color=BORDER
        )
        card.pack(fill="x", pady=4)

        ctk.CTkLabel(
            card,
            text="?? Clé d'activation",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT
        ).pack(anchor="w", padx=22, pady=(22, 8))

        self.premium_key_entry = ctk.CTkEntry(
            card,
            height=44,
            corner_radius=10,
            placeholder_text="PPC-XXXXX-XXXXX-XXXXX-XXXXX",
            font=ctk.CTkFont(size=14),
            border_width=1,
            border_color="#5A22B8"
        )
        self.premium_key_entry.pack(fill="x", padx=22, pady=(0, 12))
        self.premium_key_entry.bind("<Return>", lambda _event: self.activate_premium())

        self.premium_status_label = ctk.CTkLabel(
            card,
            text="?? La clé est valable 5 minutes et ne peut être utilisée qu'une seule fois.",
            text_color=MUTED,
            justify="left",
            wraplength=850,
            font=ctk.CTkFont(size=11)
        )
        self.premium_status_label.pack(anchor="w", padx=22, pady=(0, 14))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(0, 22))

        self.premium_activate_button = ctk.CTkButton(
            buttons,
            text="?? Activer",
            height=42,
            corner_radius=10,
            fg_color=PURPLE,
            hover_color=PURPLE_HOVER,
            command=self.activate_premium
        )
        self.premium_activate_button.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            buttons,
            text="?? Contact",
            height=42,
            corner_radius=10,
            fg_color="#30213F",
            hover_color=PURPLE_HOVER,
            # TODO: remplace par l'URL de contact/support réelle du site AtomeOpti.
            command=lambda: webbrowser.open("https://TODO-remplace-par-ton-domaine.example/contact")
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

        if self.premium_active:
            self.premium_status_label.configure(
                text="? déjà activé pour cette session pour cette session.",
                text_color=SUCCESS
            )
            self.premium_key_entry.configure(state="disabled")
            self.premium_activate_button.configure(
                text="? activation réussie",
                state="disabled"
            )

    def activate_premium(self):
        """Envoie la clé au serveur et active Premium si elle est valide."""
        if self.premium_active:
            return

        key = self.premium_key_entry.get().strip().upper()
        if not key:
            self.premium_status_label.configure(
                text="? Entre une clé d'activation.",
                text_color="#FF6B8A"
            )
            return

        self.premium_activate_button.configure(
            text="? Vérification...",
            state="disabled"
        )
        self.premium_status_label.configure(
            text="?? Vérification de la clé auprès du serveur...",
            text_color=MUTED
        )

        threading.Thread(
            target=self._activate_premium_request,
            args=(key,),
            daemon=True
        ).start()

    def _activate_premium_request(self, key):
        try:
            response = requests.post(
                f"{self.license_server_url}/activate",
                json={"key": key, "product": "premium"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            self.after(0, lambda: self._premium_activation_result(
                False,
                "? Serveur de licences inaccessible. Vérifie qu'Uvicorn est lancé.",
                None
            ))
            return
        except (ValueError, TypeError):
            self.after(0, lambda: self._premium_activation_result(
                False,
                "? Réponse invalide du serveur de licences.",
                None
            ))
            return
        except Exception as exc:
            self.after(0, lambda: self._premium_activation_result(
                False,
                f"? Erreur lors de la vérification : {exc}",
                None
            ))
            return

        if data.get("ok") is True:
            self.after(0, lambda: self._premium_activation_result(
                True,
                "? Clé valide ! Activation réussie.",
                key
            ))
            return

        reasons = {
            "invalid": "? Cette clé est invalide.",
            "already_used": "? Cette clé a déjà été utilisée.",
            "expired": "? Cette clé a expiré.",
        }
        reason = data.get("reason", "invalid")
        self.after(0, lambda: self._premium_activation_result(
            False,
            reasons.get(reason, "? Cette clé ne peut pas être utilisée."),
            None
        ))

    def _premium_activation_result(self, success, message, key):
        if not hasattr(self, "premium_status_label"):
            return

        if success:
            self.premium_active = True
            self.premium_key = key
            self.premium_status_label.configure(
                text=message,
                text_color=SUCCESS
            )
            self.premium_key_entry.configure(state="disabled")
            self.premium_activate_button.configure(
                text="? activation réussie",
                state="disabled"
            )
            messagebox.showinfo(
                "AtomeOpti",
                "?? L'activation a réussi avec succès.\n\n"
                "Les fonctions d'optimisation premium sont maintenant accessibles."
            )
        else:
            self.premium_status_label.configure(
                text=message,
                text_color="#FF6B8A"
            )
            self.premium_activate_button.configure(
                text="?? Activer",
                state="normal"
            )

    def show_windows(self):

        self.clear_content()
        self.active_menu("Windows")
        header = ctk.CTkFrame(self.content, fg_color="#110923", corner_radius=18,
                              border_width=1, border_color="#2587FF")
        header.pack(fill="x", pady=(4, 12), padx=2)
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        self.add_page_title(left, "windows.png", "Windows")
        ctk.CTkLabel(left, text="Réglages Windows orientés performance et latence.", text_color=MUTED).pack(anchor="w", pady=(3, 0))
        ctk.CTkButton(header, text="Optimiser Windows", width=180, height=42, corner_radius=10, fg_color=PURPLE, hover_color=PURPLE_HOVER, font=ctk.CTkFont(size=13, weight="bold"), command=self.optimize_all_windows).pack(side="right", padx=16)
        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.pack(fill="x", pady=5)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        def card(row, col, title, desc, button_text, command, warning=False):
            frame = ctk.CTkFrame(grid, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=18, pady=(16, 5))
            ctk.CTkLabel(frame, text=desc, text_color=MUTED, justify="left", wraplength=430).pack(anchor="w", padx=18, pady=(0, 13))
            ctk.CTkButton(frame, text=button_text, height=36, corner_radius=9, fg_color="#30213F" if warning else PURPLE, hover_color=PURPLE_HOVER, command=command).pack(anchor="w", padx=18, pady=(0, 16))
        card(0, 0, "💾 SSD / Disques", "Optimise automatiquement tous les disques fixes présents (SSD et HDD).", "💾 Optimiser les disques", self.optimize_ssd)
        card(0, 1, "🎮 Graphiques / jeux", "Active automatiquement les optimisations pour les jeux fenêtrés et désactive Game Bar/captures.", "🎮 Optimiser les jeux", self.optimize_game_settings)
        card(1, 0, "🕹️ Mode Jeu Windows", "Active directement le Mode Jeu Windows.", "🕹️ Activer le Mode Jeu", self.enable_game_mode)
        card(2, 0, "🔔 Notifications", "Désactive uniquement les notifications Windows.", "🔔 Désactiver", self.optimize_notifications)
        card(2, 1, "🖱️ Souris & clavier", "Désactive la précision améliorée du pointeur et règle le clavier sur délai court + répétition rapide.", "🖱️ Appliquer", self.optimize_mouse_keyboard)
        card(3, 0, "📹 Game Bar & Captures", "Désactive Game Bar, son ouverture avec la manette et les captures pour libérer des ressources.", "📹 Désactiver", self.optimize_game_settings)
        card(3, 1, "Intégrité de la mémoire", "Plus de performances possibles, mais moins de sécurité. Redémarrage recommandé.", "Désactiver (Admin)", self.disable_memory_integrity, warning=True)
        card(4, 0, "🔌 Périphériques USB / Souris / Clavier", "Désactive automatiquement l'économie d'énergie et le réveil pour les USB, souris et claviers compatibles.", "🔌 Appliquer", self.open_device_power_management)
        card(4, 1, "🔔 Autorisations de notifications", "Les notifications globales sont désactivées automatiquement avec le bouton Notifications & Ne pas déranger.", "🔔 Déjà inclus", self.optimize_notifications)
        card(5, 0, "🛡️ Point de restauration", "Crée un point de restauration Windows nommé « AtomeOpti Restore » avant de modifier le système.", "🛡️ Créer le point", self.create_restore_point)


    def show_uninstall(self):
        self.clear_content()
        self.active_menu("Désinstallation")

        self.create_visual_header(
            "trash.png", "Désinstallation",
            "Sélectionne les applications à retirer ou à réinstaller.",
            "#FF5C70"
        )

        apps = [
            ("Copilot", "9NHT9RB2F4HD"),
            ("Microsoft Teams", "Microsoft.Teams"),
            ("Microsoft OneDrive", "Microsoft.OneDrive"),
            ("Actualités", "Microsoft.BingNews"),
            ("Hub de commentaires", "Microsoft.WindowsFeedbackHub"),
            ("Courrier & Calendrier", "microsoft.windowscommunicationsapps"),
            ("Météo", "Microsoft.BingWeather"),
            ("Cartes", "Microsoft.WindowsMaps"),
            ("Obtenir de l'aide", "Microsoft.GetHelp"),
            ("Microsoft Clipchamp", "Clipchamp.Clipchamp"),
            ("Office Hub", "Microsoft.MicrosoftOfficeHub"),
            ("Outlook", "Microsoft.OutlookForWindows"),
            ("Skype", "Microsoft.SkypeApp"),
            ("Horloge", "Microsoft.WindowsAlarms"),
            ("Enregistreur vocal", "Microsoft.WindowsSoundRecorder"),
            ("Paint", "Microsoft.Paint"),
            ("Pense-bête", "Microsoft.MicrosoftStickyNotes"),
            ("Solitaire", "Microsoft.MicrosoftSolitaireCollection"),
            ("Astuces Windows", "Microsoft.Getstarted"),
            ("Assistance rapide", "MicrosoftCorporationII.QuickAssist"),
            ("Family", "MicrosoftCorporationII.MicrosoftFamily"),
            ("Xbox", "Microsoft.XboxApp"),
            ("Xbox Game Bar", "Microsoft.XboxGamingOverlay"),
            ("Xbox Game Speech", "Microsoft.XboxGamingSpeechWindow"),
            ("Xbox Gaming", "Microsoft.GamingApp"),
            ("RivaTuner Statistics Server", "Guru3D.RTSS"),
        ]

        # self.content gère déjà le défilement de la page.
        # Un second CTkScrollableFrame provoquait la grande zone noire visible sur la capture.
        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.pack(fill="x", pady=3)

        for c in range(4):
            grid.grid_columnconfigure(c, weight=1, uniform="uninstall")

        vars_ = {}
        for i, (label, pkg) in enumerate(apps):
            row, col = divmod(i, 4)
            v = ctk.BooleanVar(value=False)
            vars_[pkg] = v

            card = ctk.CTkFrame(
                grid, fg_color=CARD, corner_radius=13,
                border_width=1, border_color=BORDER
            )
            card.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)


            ctk.CTkLabel(
                card, image=self.colored_icon(
                    UNINSTALL_ICON_FILES.get(label, "apps.png"), (42, 42)
                ), text=""
            ).pack(side="left", padx=(10, 7), pady=14)

            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(side="left", fill="both", expand=True, padx=(0, 5), pady=12)

            ctk.CTkLabel(
                body, text=label, anchor="w", wraplength=145,
                font=ctk.CTkFont(size=12, weight="bold")
            ).pack(anchor="w")

            ctk.CTkCheckBox(
                body, text="Sélectionner", variable=v
            ).pack(anchor="w", pady=(10, 0))

        def do_action(action):
            selected = [pkg for pkg, var in vars_.items() if var.get()]
            if not selected:
                messagebox.showinfo("Désinstallation", "Sélectionne au moins une application.")
                return

            title = "Désinstaller" if action == "uninstall" else "Réinstaller"
            if not messagebox.askyesno(title, f"{title} {len(selected)} application(s) ?"):
                return

            self.show_optimization_loading(
                "Désinstallation..." if action == "uninstall" else "Réinstallation..."
            )

            def worker():
                ok = 0
                errors = []
                for pkg in selected:
                    try:
                        if self.app_uninstall_or_reinstall(pkg, action):
                            ok += 1
                        else:
                            errors.append(pkg)
                    except Exception as exc:
                        errors.append(f"{pkg}: {exc}")

                def finish():
                    self.hide_optimization_loading()
                    if errors:
                        messagebox.showwarning(
                            "PerformancePC",
                            f"{ok}/{len(selected)} opération(s) réussie(s).\n\n"
                            "Échec :\n" + "\n".join(errors[:8])
                        )
                    else:
                        messagebox.showinfo(
                            "PerformancePC",
                            f"{ok}/{len(selected)} opération(s) réussie(s)."
                        )
                    self.show_uninstall()

                self.after(0, finish)

            threading.Thread(target=worker, daemon=True).start()

        buttons = ctk.CTkFrame(self.content, fg_color="transparent")
        buttons.pack(fill="x", pady=(6, 2))

        ctk.CTkButton(
            buttons, text="Désinstaller la sélection", height=44,
            fg_color="#5A2632", hover_color="#702E3D",
            command=lambda: do_action("uninstall")
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            buttons, text="Réinstaller la sélection", height=44,
            fg_color=PURPLE, hover_color=PURPLE_HOVER,
            command=lambda: do_action("install")
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    def app_uninstall_or_reinstall(self, package_id, action):
        if package_id == "9NHT9RB2F4HD":
            if action == "uninstall":
                script = """$ErrorActionPreference = 'Continue'
$packages = @(
    Get-AppxPackage -AllUsers -Name 'Microsoft.Copilot' -ErrorAction SilentlyContinue
    Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^Microsoft\\.Copilot($|\\.)' -or
            $_.PackageFullName -match 'Microsoft\\.Copilot'
        }
) | Sort-Object PackageFullName -Unique

foreach ($pkg in $packages) {
    try {
        Remove-AppxPackage -Package $pkg.PackageFullName -AllUsers -ErrorAction Stop
    } catch {
        foreach ($user in @($pkg.PackageUserInformation)) {
            try {
                if ($user.InstallState -match 'Installed') {
                    Remove-AppxPackage -Package $pkg.PackageFullName -User $user.UserSecurityId -ErrorAction Stop
                }
            } catch {}
        }
    }
}

$provisioned = Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
    Where-Object {
        $_.DisplayName -match '^Microsoft\\.Copilot($|\\.)' -or
        $_.PackageName -match 'Microsoft\\.Copilot'
    }

foreach ($pkg in $provisioned) {
    try {
        Remove-AppxProvisionedPackage -Online -PackageName $pkg.PackageName -ErrorAction Stop | Out-Null
    } catch {}
}

try {
    winget uninstall --id 9NHT9RB2F4HD --exact --silent --accept-source-agreements --disable-interactivity | Out-Null
} catch {}

try {
    winget uninstall --name 'Microsoft Copilot' --silent --accept-source-agreements --disable-interactivity | Out-Null
} catch {}

Start-Sleep -Seconds 3

$remaining = @(
    Get-AppxPackage -AllUsers -Name 'Microsoft.Copilot' -ErrorAction SilentlyContinue
    Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^Microsoft\\.Copilot($|\\.)' -or
            $_.PackageFullName -match 'Microsoft\\.Copilot'
        }
)

$remainingProvisioned = @(Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
    Where-Object {
        $_.DisplayName -match '^Microsoft\\.Copilot($|\\.)' -or
        $_.PackageName -match 'Microsoft\\.Copilot'
    })

if ($remaining.Count -eq 0 -and $remainingProvisioned.Count -eq 0) {
    exit 0
}
exit 1
"""
                return self.run_admin_powershell_sync(script)
            return install_winget_package("9NHT9RB2F4HD")

        if package_id == "Microsoft.Teams":
            if action == "uninstall":
                script = r'''
Get-AppxPackage -AllUsers *MSTeams* -ErrorAction SilentlyContinue |
    Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue
Get-AppxPackage -AllUsers *MicrosoftTeams* -ErrorAction SilentlyContinue |
    Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue
Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue |
    Where-Object {$_.DisplayName -match "MSTeams|MicrosoftTeams"} |
    Remove-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue
'''
                appx_ok = self.run_admin_powershell_sync(script)
                winget_result = subprocess.run(
                    ["winget", "uninstall", "--id", "Microsoft.Teams", "--exact",
                     "--silent", "--accept-source-agreements", "--disable-interactivity"],
                    capture_output=True, text=True, timeout=180,
                    startupinfo=_hidden_startupinfo(),
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return appx_ok or winget_result.returncode == 0
            return install_winget_package("Microsoft.Teams")

        if action == "uninstall":
            result = subprocess.run(
                ["winget", "uninstall", "--id", package_id, "--exact",
                 "--silent", "--accept-source-agreements", "--disable-interactivity"],
                capture_output=True, text=True, timeout=180,
                startupinfo=_hidden_startupinfo(),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.returncode == 0

        return install_winget_package(package_id)

    def run_admin_powershell_sync(self, script):
        import base64
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        command = (
            f"$s=[Text.Encoding]::Unicode.GetString("
            f"[Convert]::FromBase64String('{encoded}')); "
            f"Invoke-Expression $s"
        )
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden", "-Command", command
            ],
            startupinfo=_hidden_startupinfo(),
            creationflags=subprocess.CREATE_NO_WINDOW,
            capture_output=True, text=True, timeout=180
        )
        return result.returncode == 0

    def show_cleaner(self):
        self.clear_content()
        self.active_menu("Nettoyage")
        self.create_visual_header(
            "clean.png", "Nettoyage intelligent",
            "Sélectionne ce que tu veux nettoyer avant de lancer l'analyse.",
            "#D238FF"
        )

        checks = [
            ("Fichiers temporaires Windows", "temp"),
            ("Cache navigateurs", "browser"),
            ("Corbeille", "recycle"),
            ("Cache Windows Update", "update"),
            ("Cache DNS", "dns"),
            ("Fichiers de crash", "crash"),
        ]
        vars_ = {}
        frame=ctk.CTkFrame(self.content, fg_color=CARD, corner_radius=16,
                           border_width=1, border_color="#54247F")
        frame.pack(fill="x", pady=4)
        for i,(label,key) in enumerate(checks):
            v=ctk.BooleanVar(value=True); vars_[key]=v
            ctk.CTkCheckBox(frame,text=label,variable=v).grid(row=i//2,column=i%2,sticky="w",padx=18,pady=12)

        def clean():
            selected=[k for k,v in vars_.items() if v.get()]
            if not selected: return
            self.show_optimization_loading("Nettoyage en cours...")
            script=r"""
$ErrorActionPreference='SilentlyContinue'
Remove-Item "$env:TEMP\*" -Recurse -Force
Remove-Item "$env:WINDIR\Temp\*" -Recurse -Force
Clear-RecycleBin -Force
ipconfig /flushdns | Out-Null
Stop-Service wuauserv -Force
Remove-Item "$env:WINDIR\SoftwareDistribution\Download\*" -Recurse -Force
Start-Service wuauserv
Remove-Item "$env:WINDIR\Minidump\*" -Recurse -Force
"""
            def done(success):
                self.hide_optimization_loading()
                messagebox.showinfo("PerformancePC","Nettoyage terminé.")
            self.run_admin_powershell(script,done)
        ctk.CTkButton(self.content,text="Lancer le nettoyage", height=44,
                      corner_radius=12, fg_color=PURPLE,
                      hover_color=PURPLE_HOVER, command=clean).pack(anchor="w",pady=12)


    def show_startup(self):
        self.clear_content()
        self.active_menu("Démarrage")

        self.create_visual_header(
            "rocket.png", "Démarrage Windows",
            "Gère les applications et services lancés à l'ouverture de session.",
            "#00BFFF"
        )

        import winreg

        ctk.CTkLabel(
            self.content, text="Applications de démarrage",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(4, 8))

        apps_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        apps_frame.pack(fill="x", pady=(0, 12))
        for col in range(2):
            apps_frame.grid_columnconfigure(col, weight=1, uniform="startup_apps")

        items = []
        run_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "HKLM 32-bit"),
        ]

        for root, path, label in run_paths:
            try:
                with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
                    index = 0
                    while True:
                        try:
                            name, value, value_type = winreg.EnumValue(key, index)
                            approved_path = (
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32"
                                if "32-bit" in label
                                else r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
                            )
                            items.append({
                                "Name": name,
                                "Command": str(value),
                                "Location": f"Registry:{label}",
                                "root": root,
                                "path": path,
                                "value_type": value_type,
                                "approved_path": approved_path,
                                "enabled": self.get_startup_approved_state(name, approved_path),
                            })
                            index += 1
                        except OSError:
                            break
            except OSError:
                pass

        startup_dirs = [
            (Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup", "Dossier utilisateur"),
            (Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs/StartUp", "Dossier commun"),
        ]
        for folder, label in startup_dirs:
            try:
                if folder.exists():
                    for file_path in folder.iterdir():
                        if file_path.is_file() or file_path.is_symlink():
                            items.append({
                                "Name": file_path.stem,
                                "Command": str(file_path),
                                "Location": label,
                                "folder": True,
                                "path": file_path,
                                "enabled": True,
                            })
            except Exception:
                pass

        for i, item in enumerate(items):
            row, col = divmod(i, 2)
            card = ctk.CTkFrame(
                apps_frame, fg_color=CARD, corner_radius=13,
                border_width=1, border_color=BORDER
            )
            card.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)


            ctk.CTkLabel(
                card, image=self.colored_icon("apps.png", (30, 30)), text=""
            ).pack(side="left", anchor="n", padx=(12, 0), pady=14)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, padx=8, pady=10)

            ctk.CTkLabel(
                info, text=item["Name"],
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w"
            ).pack(anchor="w")
            ctk.CTkLabel(
                info, text=item["Location"],
                text_color="#A56DFF",
                font=ctk.CTkFont(size=9, weight="bold"),
                anchor="w"
            ).pack(anchor="w", pady=(2, 3))
            ctk.CTkLabel(
                info, text=item["Command"][:150],
                text_color=MUTED, wraplength=360, justify="left", anchor="w"
            ).pack(anchor="w")

            variable = ctk.BooleanVar(value=item["enabled"])
            def app_changed(x=item, var=variable):
                self.toggle_startup_item(x, bool(var.get()))

            ctk.CTkSwitch(
                card, text="", variable=variable,
                onvalue=True, offvalue=False, width=45,
                progress_color=PURPLE,
                button_color="#E8E2F5",
                button_hover_color="#FFFFFF",
                command=app_changed
            ).pack(side="right", padx=14, pady=(18, 0))

        ctk.CTkLabel(
            self.content, text="Services Windows",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w", pady=(14, 8))
        ctk.CTkLabel(
            self.content,
            text="Services configurés pour démarrer automatiquement avec Windows. "
                 "Les désactiver ne les désinstalle pas.",
            text_color=MUTED, justify="left", wraplength=900
        ).pack(anchor="w", pady=(0, 8))

        services_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        services_frame.pack(fill="x", pady=(0, 10))
        for col in range(2):
            services_frame.grid_columnconfigure(col, weight=1, uniform="startup_services")

        services = []
        try:
            raw = powershell(r'''
Get-CimInstance Win32_Service |
    Where-Object { $_.StartMode -in @("Auto","Boot","System") } |
    Select-Object Name,DisplayName,State,StartMode |
    Sort-Object DisplayName |
    ConvertTo-Json -Compress
''')
            services = json.loads(raw) if raw else []
            if isinstance(services, dict):
                services = [services]
        except Exception:
            services = []

        for i, service in enumerate(services):
            row, col = divmod(i, 2)
            service_name = str(service.get("Name") or "")
            display_name = str(service.get("DisplayName") or service_name)
            state = str(service.get("State") or "Unknown")
            start_mode = str(service.get("StartMode") or "Auto")

            card = ctk.CTkFrame(
                services_frame, fg_color=CARD, corner_radius=12,
                border_width=1, border_color=BORDER, height=108
            )
            card.grid(row=row, column=col, sticky="nsew", padx=5, pady=4)


            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, padx=13, pady=10)
            ctk.CTkLabel(
                info, text=display_name[:55],
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w"
            ).pack(anchor="w")
            ctk.CTkLabel(
                info, text=f"{service_name} • {start_mode} • {state}",
                text_color=MUTED, font=ctk.CTkFont(size=9), anchor="w"
            ).pack(anchor="w", pady=(3, 0))

            variable = ctk.BooleanVar(value=True)
            def service_changed(svc=service_name, original=start_mode, var=variable):
                self.toggle_windows_service(svc, original, bool(var.get()))
            ctk.CTkSwitch(
                card, text="", variable=variable,
                onvalue=True, offvalue=False, width=45,
                progress_color=PURPLE,
                button_color="#E8E2F5",
                button_hover_color="#FFFFFF",
                command=service_changed
            ).pack(side="right", padx=14, pady=(18, 0))

        ctk.CTkLabel(
            self.content,
            text=f"{len(items)} application(s) + {len(services)} service(s) détectés.",
            text_color=MUTED, font=ctk.CTkFont(size=10)
        ).pack(anchor="w", pady=(4, 10))

    def get_startup_approved_state(self, name, approved_path):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, approved_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, name)
                if isinstance(value, (bytes, bytearray)) and value:
                    return value[0] != 0x03
        except OSError:
            pass
        return True

    def set_startup_approved_state(self, name, approved_path, enabled):
        import winreg
        data = bytes([0x02, 0, 0, 0, 0, 0, 0, 0]) if enabled else bytes([0x03, 0, 0, 0, 0, 0, 0, 0])
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, approved_path) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, data)

    def toggle_windows_service(self, service_name, original_start_mode, enabled):
        mapping = {"Auto": "auto", "Boot": "boot", "System": "system"}
        start_type = mapping.get(original_start_mode, "auto") if enabled else "disabled"
        try:
            result = subprocess.run(
                ["sc.exe", "config", service_name, "start=", start_type],
                capture_output=True, text=True, timeout=30,
                startupinfo=_hidden_startupinfo(),
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "sc.exe a échoué")
            self.after(100, self.show_startup)
        except Exception as exc:
            messagebox.showerror("Services Windows", f"Impossible de modifier « {service_name} » :\n\n{exc}")
            self.after(100, self.show_startup)

    def toggle_startup_item(self, item, enabled):
        try:
            if item.get("folder"):
                # Le dossier Startup n'a pas exactement le même mécanisme
                # StartupApproved que Registry\Run. On conserve la compatibilité
                # avec l'ancien système pour ces raccourcis/fichiers.
                src = Path(item["path"])
                disabled = Path(os.environ.get("APPDATA", str(Path.home()))) / "PerformancePC" / "DisabledStartup"
                disabled.mkdir(parents=True, exist_ok=True)
                if enabled:
                    candidate = disabled / src.name
                    if candidate.exists() and not src.exists():
                        import shutil
                        shutil.move(str(candidate), str(src))
                elif src.exists():
                    import shutil
                    shutil.move(str(src), str(disabled / src.name))
            else:
                # Pour Registry\Run, la valeur reste intacte.
                # Seul StartupApproved est modifié.
                approved_path = item.get("approved_path")
                if not approved_path:
                    approved_path = (
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\StartupApproved\Run"
                    )
                self.set_startup_approved_state(item["Name"], approved_path, enabled)

            self.after(0, self.show_startup)

        except Exception as exc:
            messagebox.showerror(
                "Démarrage",
                f"Impossible de modifier ce programme :\n\n{exc}"
            )
            self.after(0, self.show_startup)

    def disable_startup_item(self, item):
        self.toggle_startup_item(item, False)

    def restart_as_admin(self):
        try:
            import sys
            params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
            executable = Path(sys.executable).with_name("pythonw.exe")
            if not executable.exists():
                executable = Path(sys.executable)
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(executable), f'"{Path(__file__).resolve()}" {params}'.strip(), str(Path(__file__).resolve().parent), 1)
            if result > 32:
                self.destroy()
            else:
                raise RuntimeError(f"Windows a refusé l'élévation (code {result}).")
        except Exception as exc:
            messagebox.showerror("PerformancePC", str(exc))

    def on_close(self):
        self.monitor_running = False
        self.destroy()


if __name__ == "__main__":
    # Pas d'élévation automatique au lancement :
    # cela évite que pythonw.exe relance le programme puis disparaisse.
    try:
        app = PerformancePC()
        app.protocol("WM_DELETE_WINDOW", app.on_close)
        app.mainloop()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            messagebox.showerror(
                "AtomeOpti - erreur au démarrage",
                f"{type(exc).__name__}: {exc}\n\n"
                "Lance le programme avec python.exe depuis VS Code pour voir le détail."
            )
        except Exception:
            pass





