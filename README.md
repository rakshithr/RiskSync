# RiskSync: Copiador de Trades para MetaTrader 5 (Local)

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-informational)

**RiskSync** es una aplicación de línea de comandos en Python diseñada para replicar operaciones de trading desde una cuenta "master" de MetaTrader 5 hacia múltiples cuentas "slave" en el mismo equipo Windows. Utiliza un método de **sondeo rápido (fast polling)** para una sincronización casi en tiempo real.

---

## 🚀 Características Principales

- **Sincronización Master → Slaves:** Copia, modifica y cierra operaciones de una cuenta principal a una o más cuentas secundarias.
- **Sondeo Rápido:** Intervalos de bucle configurables (ej. 0.1s) para una reacción casi instantánea a los cambios en la cuenta master.
- **Cálculo de Lotaje por Riesgo:** Calcula automáticamente el tamaño del lote para cada cuenta slave basándose en un riesgo monetario (USD) definido por operación.
- **Gestión de Stop Loss:** Obliga a que las operaciones tengan un Stop Loss para ser copiadas, como medida de gestión de riesgo.
- **Actualizaciones Automáticas:** Sincroniza las modificaciones de SL/TP y cierra las posiciones en las cuentas slaves cuando se cierran en la master.
- **Persistencia de Estado:** Utiliza un archivo `state.json` para llevar un registro de las operaciones copiadas, evitando duplicados incluso si el script se reinicia.
- **Configuración Centralizada:** Toda la configuración de cuentas, rutas y riesgos se gestiona desde un único archivo `config.json`.
- **100% Local:** No depende de servidores externos, APIs web ni DLLs adicionales. Toda la comunicación ocurre localmente en tu máquina.
- **Soporte Multi-Terminal:** Cada cuenta puede tener asignada una ruta de `terminal64.exe` diferente, permitiendo operar con distintos brokers simultáneamente.

---

## ⚙️ ¿Cómo Funciona?

El flujo del sistema es simple y robusto:

1.  **Inicialización:** El script carga la configuración de `config.json` y el estado de las operaciones ya copiadas desde `state.json`. Luego, establece conexión con la cuenta master y las cuentas slaves.
2.  **Bucle de Sondeo:** Entra en un bucle infinito que se ejecuta cada `loop_interval` segundos.
3.  **Detección de Cambios:**
    - **Nuevas Operaciones:** Compara las posiciones abiertas en la cuenta master con las registradas en `state.json`. Si una operación no está en el estado, es nueva.
    - **Operaciones Cerradas:** Si una operación registrada en `state.json` ya no está abierta en la master, se marca para cierre.
    - **Modificaciones:** Revisa si el SL o TP de una operación existente ha cambiado.
4.  **Ejecución de Órdenes:**
    - Para **nuevas operaciones**, calcula el lotaje según el riesgo y las copia en cada slave.
    - Para **operaciones cerradas**, envía la orden de cierre a las slaves correspondientes.
    - Para **modificaciones**, actualiza el SL/TP en las slaves.
5.  **Actualización de Estado:** Cualquier operación nueva o cerrada se registra en `state.json` para mantener la consistencia.

---

## 📂 Estructura de Archivos

```
RiskSync/
│
├── config.json          # Configuración de cuentas, rutas y riesgos
├── main.py              # Script principal que ejecuta la lógica
├── requirements.txt     # Dependencias de Python
├── state.json           # Cache de operaciones copiadas (creado automáticamente)
└── logs/
    └── RiskSync.log   # Registro de eventos (creado automáticamente)
```

---

## 📋 Requisitos

-   Sistema Operativo Windows.
-   Python 3.11 o superior.
-   Una o más terminales de MetaTrader 5 instaladas.
-   La librería `MetaTrader5` para Python.

---

## 🛠️ Instalación y Configuración

1.  **Clona el repositorio:**
    ```bash
    git clone https://github.com/tu-usuario/RiskSync.git
    cd RiskSync
    ```

2.  **Instala las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configura las cuentas en `config.json`:**
    Este es el paso más importante. Abre el archivo `config.json` y edítalo con tus datos.

    ```json
    {
      "master": {
        "login": 123456,
        "password": "PasswordMaster",
        "server": "Broker-Server",
        "mt5_path": "C:/Program Files/MetaTrader 5/terminal64.exe"
      },
      "slaves": [
        {
          "login": 654321,
          "password": "PasswordSlave1",
          "server": "Broker-Server-2",
          "mt5_path": "C:/Users/Admin/AppData/Roaming/MetaQuotes/Terminal/ABC.../terminal64.exe",
          "risk_usd": 50
        }
      ],
      "loop_interval": 0.1,
      "ignore_no_sl": true,
      "trade_comment": "RiskSync"
    }
    ```
    -   `login`, `password`, `server`: Tus credenciales de MT5.
    -   `mt5_path`: **(CRÍTICO)** La ruta absoluta al archivo `terminal64.exe` de la terminal que quieres usar para esa cuenta. Esto es fundamental para conectar con el broker correcto.
    -   `risk_usd`: La cantidad de dinero que estás dispuesto a arriesgar en cada operación para esa cuenta slave.
    -   `loop_interval`: El tiempo en segundos entre cada ciclo de sondeo.
    -   `ignore_no_sl`: Si es `true`, no se copiarán operaciones que no tengan un Stop Loss definido en la cuenta master.

---

## ▶️ Uso

Una vez configurado, simplemente ejecuta el script principal desde tu terminal:

```bash
python main.py
```

El script comenzará a ejecutarse y mostrará los logs en la consola. Puedes detenerlo en cualquier momento con `Ctrl + C`.

---

## ⚠️ Descargo de Responsabilidad

Este software se proporciona "tal cual", sin garantías de ningún tipo. El trading de instrumentos financieros conlleva un alto nivel de riesgo y puede no ser adecuado para todos los inversores. Antes de utilizar esta herramienta con dinero real, pruébala exhaustivamente en **cuentas demo**. El autor no se hace responsable de ninguna pérdida financiera.
