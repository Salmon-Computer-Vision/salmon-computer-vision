# Requirements

- Python 3
- Numpy
- pillow
- tqdm
- Pytz
- ffmpeg

Please recurse the submodules to also clone pyARIS in the same folder:
```
git submodule update --init --recursive
```

If using Anaconda to manage packages run the following:

Create environment:
```
conda create --name pyaris
conda activate pyaris
```

Install packages
```
conda install numpy
conda install -c anaconda pillow
conda install -c conda-forge ffmpeg tqdm pytz opencv
```

## Troubleshooting
If you get the error of "Failed to create temp directory,"
this is due to spaces in your username.

To fix as outlined [here](https://stackoverflow.com/questions/60789886/error-failed-to-create-temp-directory-c-users-user-appdata-local-temp-conda),
you need to set the `TMP` and `TEMP` environment variables
to something like `C:\Temp` with no spaces in the filepath.

If you do not have permissions to change your USER environment variables,
you can set them temporarily for that terminal session with
```
set TMP=C:\Temp
set TEMP=C:\Temp
```
