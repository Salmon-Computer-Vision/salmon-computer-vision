# -*- mode: python ; coding: utf-8 -*-

# For https://github.com/hunglc007/tensorflow-yolov4-tflite.git
import os.path as osp


block_cipher = None
conda_base = "C:/Users/samim/Anaconda3/envs/tf/Library/bin/"


a = Analysis(['detectvideo.py'],
             pathex=["C:\\Users\\samim\\Documents\\CMPT\\CMPT Master's Thesis\\tensorflow-yolov4-tflite"],
             binaries=[
               (osp.join(conda_base, 'cublas64_10.dll'), '.'),
               (osp.join(conda_base, 'cublasLt64_10.dll'), '.'),
               (osp.join(conda_base, 'cusolver64_10.dll'), '.'),
               (osp.join(conda_base, 'cusparse64_10.dll'), '.'),
               (osp.join(conda_base, 'nvToolsExt64_1.dll'), '.'),
               (osp.join(conda_base, 'nvrtc64_101_0.dll'), '.'),
               (osp.join(conda_base, 'cudart64_101.dll'), '.'),
               (osp.join(conda_base, 'cufft64_10.dll'), '.'),
               (osp.join(conda_base, 'cufftw64_10.dll'), '.'),
               (osp.join(conda_base, 'curand64_10.dll'), '.'),
               (osp.join(conda_base, 'cudnn64_7.dll'), '.'),

               ('./data/classes/obj.names', './data/classes'),
               ],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='detectvideo',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='detectvideo')
