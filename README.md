
# annotate_translation
A text annotation tool for translating and annotating entity alignments

## Installation

Download the binary for your OS from [here](https://github.com/kleag/annotate_translation/releases/tag/v0.1.5). 
Currently, Linux, macOS and Windows are supported.

## Usage
Pip install requirements:
```
conda create -n qt5 python=3.8
conda activate qt5

git clone https://github.com/danovw/annotate_translation.git
cd annotate_translation
pip install -r requirements.txt
```

Then:
```
python annotation.py
```

## Stand-alone executable
Since the tool is written in PyQt, you can easily package it as a Windows, Macos, Linux application.

Make sure you have installed PyInstaller: `pip install -U pyinstaller`.

Then:
```
pyinstaller -F -w annotation.py
```
The executable will appear in the "dist" directory
