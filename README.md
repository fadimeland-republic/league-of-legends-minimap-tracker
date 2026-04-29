# League Minimap champion tracker

League Minimap Champion Tracker (YOLOv11)

---

## ✨ Features

 
Real-Time Tracking: High-speed champion detection using the latest YOLOv11 architecture.

Custom Alarm Zones: Draw and configure specific "danger zones" (like river brushes or jungle entrances) to get notified of incoming ganks.

Dynamic Configuration: Easily adjust your minimap capture area and zone sensitivity on the fly.

Bird’s Eye Intelligence: Translates raw pixels into actionable alerts for better decision-making.
   
---

## 🛠️ Requirements

- Ultralytics 8.3+

- Python 3.8+

- Mss 9.0+

- Pillow 10+

- Opencv-python 4.9+

- Numpy 1.26+

Install dependencies:

```bash
InstallRequirements.bat
```
---
## Usage
🚀 Getting Started
1. Installation
Clone the repository and install the necessary dependencies using the provided batch file

2. Configure Your Danger Zones
Before running the tracker, you need to tell the script which areas of the map to monitor (e.g., Top/Bot river).

Run ZoneDrawer.py.

Draw your desired detection zones over your minimap.

Click Save (zones.json) to export your configuration.

3. Run the Tracker
Once your zones are set, launch the main application:

Run BirdEye.py.

Click the Browse button and select your trained model file (e.g., best.pt).

Load your saved zones by clicking Zone Load.

Adjust the minimap capture area in the UI if necessary.

Click Start to begin tracking.

⚠️ Disclaimer
This tool is intended for educational and analytical purposes. Using third-party tools that interact with or monitor game state may violate the Terms of Service of the game developer. Use at your own risk.
---

## Example

![img_00001]([https://github.com/user-attachments/assets/17340b96-2a5f-4d7e-b95a-7f184e17749d](https://github.com/fadimeland-republic/league-of-legends-minimap-tracker/blob/6e6e1a9e85017a41cc2497035390a495a0f30301/Example2.png))

![img_00001]([[https://github.com/user-attachments/assets/17340b96-2a5f-4d7e-b95a-7f184e17749d](https://github.com/fadimeland-republic/league-of-legends-minimap-tracker/blob/6e6e1a9e85017a41cc2497035390a495a0f30301/Example2.png](https://github.com/fadimeland-republic/league-of-legends-minimap-tracker/blob/6e6e1a9e85017a41cc2497035390a495a0f30301/Example1.png)))
