# PyTeste
<div align="center">
  <a href="https://github.com/RochaSWallace/pyteste">
    <img width="450" src="https://i.imgur.com/RWMFT6o.png" />
  </a>
</div>

A cross-platform manga downloader for **Linux, Windows, and MacOS**, based on [Pyneko](https://github.com/Lyem/pyneko). It incorporates code from **SmartStitch** for advanced image slicing, ensuring fast and seamless downloads.

<a href="https://github.com/RochaSWallace/pyteste/releases">
    <img src="https://img.shields.io/github/downloads/Lyem/pyneko/total" />
</a>&nbsp;&nbsp;

## Dependencies  

🌎 **Global**: Chrome  

🐧 **Linux/BSD**:  
  - **KDE**: Native support (requires `dbus`, `klipper`, and `dbus-python`, usually pre-installed).  
  - **X11**: Install `xsel` or `xclip`  
    ```bash
    sudo zypper install xsel  # or  
    sudo zypper install xclip  
    ```  
  - **Wayland**: Install `wl-clipboard`  
    ```bash
    sudo zypper install wl-clipboard  
    ```

## Development Commands
 
```bash
poetry install    # Install dependencies  
poetry run start  # Start the application  
poetry run build  # Build the project  
poetry run clean  # Clean __pycache__  
poetry run new    # Create a new provider  
```

## Credits

This project uses code from the [SmartStitch](https://github.com/MechTechnology/SmartStitch) for image slicing.

