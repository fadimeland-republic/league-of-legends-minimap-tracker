# League Minimap champion tracker

Computer vision model made with yolov11

---

## Features

  - Can track champions on minimap and send alarms
  - Modifiable detection alarm zones
   
---

## Requirements

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
##Usage
1.Install dependencies with InstallRequirements.bat
2.Run ZoneDrawer.py and configure top and bot river zones on your minimap
3.Click Save(zones.json) to save zone json file
4.Run BirdEye.py select best.pt with browse button
5.Configure minimap area if needed
6.Click Zone load to load zones.json
7.Click Start button
---

## A Generated Image

![img_00001](https://github.com/user-attachments/assets/17340b96-2a5f-4d7e-b95a-7f184e17749d)

## Debug View of the Image Showing Labels

![debug_img_00001](https://github.com/user-attachments/assets/25212c5e-5adc-48cb-ac19-389310c69245)


