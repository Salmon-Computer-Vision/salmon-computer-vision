# Run Towards-Realtime-MOT Inference Model

### 1. Git clone MOT code

We want to git clone MOT code. The code has been modified to work with fish instead of the human face.

Git clone the salmon branch that has the changes:

[Salmon-Computer-Vision/Towards-Realtime-MOT](https://github.com/Salmon-Computer-Vision/Towards-Realtime-MOT/tree/salmon)

### 2. Install WSL2

MOT code works the best in a Linux environment. If we do not have a Linux system, we can use WSL2.

Follow this guidance to install WSL2 for Windows 10.

[Install WSL on Windows 10](https://docs.microsoft.com/en-us/windows/wsl/install-win10)

### 3. Access WSL2

To access WSL2, we can install Windows Terminal. Open Windows Terminal and type:

```powershell
wsl
```

Then, WSL2 will start running, and our terminal will connect to WSL2. Note that our Windows 10 C drive is mounted to WSL2 at the location of:

```powershell
/mnt/c/
```

We can access the mounted C drive to get files from or move files to our Windows 10 system.

### 4. Install CUDA for WSL2

We need to use CUDA in WSL2 to run MOT. To let WSL2 access GPU, we need to install Windows 10 Insider Version. After installing Windows Insider Version, we can download the GPU drivers in our Windows 10, and then WSL2 can automatically access GPU. 

Follow this guide to set up CUDA:

[CUDA on WSL :: CUDA Toolkit Documentation](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)

### 5. Prepare input video and weight

Have input video and the trained weights ready to run MOT.

### 6. Run MOT using a command

Use this command to run MOT in WSL2.

Note that we need to specify the path of the input video, weights, and the output folder path. Also, we need to specify the configuration file path.

```powershell
python3 demo.py --input-video ~/salmon_fish_files/input_videos/input.mp4 --weights ~/salmon_fish_files/weights/latest.pt --output-format video --output-root ~/salmon_fish_files/output/ --cfg cfg/yolov3.cfg
```
