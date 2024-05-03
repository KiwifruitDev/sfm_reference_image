# SFM Reference Image
# A script that uses image APIs or a custom URL to display images in Source Filmmaker.
# https://github.com/KiwifruitDev/sfm_reference_image
# https://steamcommunity.com/sharedfiles/filedetails/?id=3238130704
# Based on https://github.com/KiwifruitDev/sfm_sample_script
# This software is licensed under the MIT License.
# Copyright (c) 2024 KiwifruitDev

import sfm
from vs import movieobjects
import sfmApp
from PySide import QtGui, QtCore, shiboken

import os
import json
import threading
import subprocess
import win32gui
import win32process
import win32ui
import win32con
from atexit import register

try:
    sfm
except NameError:
    from sfm_runtime_builtins import *

ProductName = "Reference Image"
InternalName = "reference_image"

animals = {
    "API: Dog (Random Breed)": "https://dog.ceo/api/breeds/image/random",
    "API: Dog (Shiba Inu)": "http://shibe.online/api/shibes?count=1&urls=true",
    "API: Frinkiac (Simpsons Screenshots)": "https://frinkiac.com/api/random",
    "Custom": "",
    #"Window": "",
}

def GetImageUrl(animal, data):
    if animal == "API: Dog (Random Breed)":
        return data.get("message")
    elif animal == "API: Dog (Shiba Inu)":
        return data[0]
    elif animal == "API: Frinkiac (Simpsons Screenshots)":
        url = "https://frinkiac.com/img/%s/%s.jpg"
        frame = data.get("Frame")
        if frame is None:
            return None
        return url % (frame.get("Episode"), frame.get("Timestamp"))
    return None

class AnimalWindow(QtGui.QWidget):
    def __init__(self):
        super( AnimalWindow, self ).__init__()
        self.hwnd = None
        self.wdc = None
        self.addosc = 0
        self.addoscsub = False
        self.addoscmin = -5
        self.addoscmax = 5
        self.imageext = "jpg"
        self.busy = 0
        self.currentCustom = ""
        self.pid = 0
        self.currentpid = -1
        self.thread = None
        self.thread2 = None
        self.initUI()
        # Timer
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.Poke)
        self.timer.start(1)
        register(self.timer.stop)
        # Event filter
        self.installEventFilter(self)
    def eventFilter(self, obj, event):
        # Listen for Ctrl+Shift+V to paste image
        if event.type() == QtCore.QEvent.KeyRelease:
            if event.key() == QtCore.Qt.Key_V and event.modifiers() == QtCore.Qt.ControlModifier:
                clipboard = QtGui.QApplication.clipboard()
                image = clipboard.image()
                if not image.isNull():
                    image.save("temp.png")
                    self.imagepath = "temp.png"
                    self.busy = 2
                    return True
        self.Poke()
        return False
    def initUI(self):
        baselayout = QtGui.QVBoxLayout()
        self.setLayout(baselayout)
        toplayout = QtGui.QHBoxLayout()
        baselayout.addLayout(toplayout)
        # Label
        label = QtGui.QLabel("Preset:")
        toplayout.addWidget(label)
        topsublayout = QtGui.QVBoxLayout()
        toplayout.addLayout(topsublayout)
        topsublayout2 = QtGui.QVBoxLayout()
        toplayout.addLayout(topsublayout2)
        # Choice box for animal (and api domain)
        self.animalChoice = QtGui.QComboBox()
        for animal in animals:
            self.animalChoice.addItem(animal)
        indexes = {}
        # Get order inside self.animalChoice
        for i in range(self.animalChoice.count()):
            indexes[self.animalChoice.itemText(i)] = i
        # Set to custom
        self.animalChoice.setCurrentIndex(indexes["Custom"])
        self.animalChoice.currentIndexChanged.connect(self.ChoiceChanged)
        topsublayout.addWidget(self.animalChoice)
        # API domain text entry box
        self.apiDomain = QtGui.QLineEdit()
        self.apiDomain.setPlaceholderText("Load/paste an image or type an image URL.")
        self.apiDomain.setText(animals[self.animalChoice.currentText()])
        self.apiDomain.textChanged.connect(self.ApiDomainChanged)
        topsublayout.addWidget(self.apiDomain)
        # Hidden choice box
        self.windowChoice = QtGui.QComboBox()
        self.windowChoice.currentIndexChanged.connect(self.WindowChoiceChanged)
        self.windowChoice.hide()
        topsublayout.addWidget(self.windowChoice)
        # Button to get image
        self.getImageButton = QtGui.QPushButton("Download Image")
        self.getImageButton.clicked.connect(self.GetImage)
        topsublayout2.addWidget(self.getImageButton)
        # Button to load image
        self.loadImageButton = QtGui.QPushButton("Load Image")
        self.loadImageButton.clicked.connect(self.LoadImage)
        topsublayout2.addWidget(self.loadImageButton)
        # Image
        self.image = QtGui.QLabel()
        self.image.setScaledContents(True)
        baselayout.addWidget(self.image)
        # Black pixmap
        self.pixmap = QtGui.QPixmap(1, 1)
        self.pixmap.fill(QtCore.Qt.black)
        self.image.setPixmap(self.pixmap)
        self.currentWidth = self.image.width()
        self.currentHeight = self.image.height()
    def ChoiceChanged(self):
        animal = self.animalChoice.currentText()
        if animal == "Custom":
            self.busy = 0
            self.apiDomain.show()
            self.apiDomain.setText(self.currentCustom)
            self.apiDomain.setEnabled(True)
            self.loadImageButton.setEnabled(True)
            self.getImageButton.setEnabled(True)
            self.windowChoice.hide()
            self.windowChoice.clear()
            self.windowChoice.setEnabled(True)
        elif animal == "Window":
            self.busy = -1
            self.apiDomain.hide()
            self.apiDomain.setText("")
            self.apiDomain.setEnabled(False)
            self.loadImageButton.setEnabled(False)
            self.getImageButton.setEnabled(False)
            self.windowChoice.show()
            self.windowChoice.setEnabled(True)
            self.PopulateWindows()
        else:
            self.busy = 0
            self.apiDomain.show()
            self.apiDomain.setEnabled(False)
            self.apiDomain.setText(animals[animal])
            self.loadImageButton.setEnabled(False)
            self.getImageButton.setEnabled(True)
            self.windowChoice.hide()
            self.windowChoice.clear()
            self.windowChoice.setEnabled(True)
    def PopulateWindows(self):
        if os.path.exists("screenshot.bmp"):
            os.remove("screenshot.bmp")
        self.windowChoice.clear()
        # TODO: Populate window choice
        self.windowChoice.addItem("(#2380)")
    def WindowChoiceChanged(self):
        # Get PID from choice name in parentheses after last #
        # Example: "Source Filmmaker (#12345)"
        window = self.windowChoice.currentText()
        if window == "":
            return
        self.pid = int(window.split("#")[-1].split(")")[0])
        if self.currentpid != self.pid:
            self.currentpid = self.pid
            # Release resources
            if self.wdc is not None:
                win32gui.ReleaseDC(self.hwnd, self.wdc)
            if self.hwnd is not None:
                win32gui.DeleteObject(self.hwnd)
            self.hwnd = None
            self.wdc = None
        if self.hwnd is None:
            self.hwnd = self.FindWindow(self.pid)
        if self.hwnd is not None:
            if self.wdc is None:
                self.wdc = win32gui.GetWindowDC(self.hwnd)
        if self.wdc is not None and self.hwnd is not None:
            self.StartWindowCapture()
    def StartWindowCapture(self):
        if os.path.exists("screenshot.bmp"):
            os.remove("screenshot.bmp")
        self.thread2 = threading.Thread(target=self.CaptureWindow)
        self.thread2.start()
        register(self.thread2.join)
    def FindWindow(self, pid):
        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    hwnds.append(hwnd)
            return True
        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        return hwnds[0] if hwnds else None
    def CaptureWindow(self):
        if self.pid == 0:
            return
        if self.busy == -2:
            return
        # Capture window by pid
        if self.hwnd is not None and self.wdc is not None:
            # Capture window
            dcObj = win32ui.CreateDCFromHandle(self.wdc)
            dataBitMap = win32ui.CreateBitmap()
            cDC = dcObj.CreateCompatibleDC()
            # Get window size
            left, top, right, bot = win32gui.GetClientRect(self.hwnd)
            w = right - left
            h = bot - top
            # Resize to self.current and maintain aspect ratio
            widgetwidth = self.currentWidth
            widgetheight = self.currentHeight
            if w * widgetheight > widgetwidth * h:
                newwidth = widgetwidth
                newheight = widgetwidth * h / w
            else:
                newheight = widgetheight
                newwidth = widgetheight * w / h
            # Create bitmap and save image (must be resized to fit in self.currentWidth and self.currentHeight)
            dataBitMap.CreateCompatibleBitmap(dcObj, newwidth + self.addosc, newheight + self.addosc)
            cDC.SelectObject(dataBitMap)
            cDC.StretchBlt([0, 0], [newwidth, newheight], dcObj, [0, 0], [w, h], win32con.SRCCOPY)
            dataBitMap.SaveBitmapFile(cDC, "screenshot.bmp")
            # Clean up
            dcObj.DeleteDC()
            cDC.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, self.wdc)
            win32gui.DeleteObject(dataBitMap.GetHandle())
        if self.busy == -1:
            self.busy = -2
    def ApiDomainChanged(self):
        if self.animalChoice.currentText() == "Custom":
            self.currentCustom = self.apiDomain.text()
    def Poke(self):
        busy = self.busy
        # Add oscillation from self.addoscmin to self.addoscmax
        if self.addoscsub:
            #self.addosc -= 1
            if self.addosc <= self.addoscmin:
                self.addoscsub = False
        else:
            #self.addosc += 1
            if self.addosc >= self.addoscmax:
                self.addoscsub = True
        # Poke threads if busy
        if busy == 1:
            if self.thread is not None:
                # Get info about the thread
                threadinfo = threading._active.get(self.thread.ident)
        elif busy == 2:
            self.busy = 0
            # Apply image
            self.ApplyImage()
            self.Cleanup()
        # Errors
        elif busy == 3:
            self.busy = 0
            self.Cleanup()
            ShowMessageBox("Please enter an image URL.", Warning)
        elif busy == 4:
            self.busy = 0
            self.Cleanup()
            ShowMessageBox("Failed to get animal data.", Warning)
        elif busy == 5:
            self.busy = 0
            self.Cleanup()
            ShowMessageBox("Failed to get image URL from API.", Warning)
        elif busy == 6:
            self.busy = 0
            self.Cleanup()
            ShowMessageBox("Failed to get image.", Warning)
        #elif busy == 0:
        elif busy == -1:
            if self.thread2 is not None:
                # Get info about the thread
                threadinfo = threading._active.get(self.thread2.ident)
            self.KeepAspectRatio()
        elif busy == -2:
            self.busy = -1
            # temp.bmp
            if os.path.exists("screenshot.bmp"):
                self.imagepath = "screenshot.bmp"
                self.ApplyImage()
                self.Cleanup()
            # Timer: 0.25 seconds to StartWindowCapture
            self.StartWindowCapture()
        else:
            self.KeepAspectRatio()
    def ApplyImage(self):
        self.pixmap = QtGui.QPixmap(self.imagepath)
        self.KeepAspectRatio(True)
    def KeepAspectRatio(self, force=False):
        # Draw image with aspect ratio
        if self.pixmap.isNull():
            return
        widgetwidth = self.image.width()
        widgetheight = self.image.height()
        # When the current width and height are different from self.image.width() and self.image.height()
        if self.currentWidth != widgetwidth or self.currentHeight != widgetheight or force:
            pixmapwidth = self.pixmap.width()
            pixmapheight = self.pixmap.height()
            # Maintain aspect ratio by adding letterbox or pillarbox
            if pixmapwidth * widgetheight > widgetwidth * pixmapheight:
                # Pillarbox
                newwidth = widgetwidth
                newheight = widgetwidth * pixmapheight / pixmapwidth
                x = 0
                y = (widgetheight - newheight) / 2
            else:
                # Letterbox
                newheight = widgetheight
                newwidth = widgetheight * pixmapwidth / pixmapheight
                x = (widgetwidth - newwidth) / 2
                y = 0
            # Draw
            newpixmap = QtGui.QPixmap(widgetwidth, widgetheight)
            newpixmap.fill(QtCore.Qt.black)
            painter = QtGui.QPainter(newpixmap)
            painter.drawPixmap(x, y, newwidth, newheight, self.pixmap)
            painter.end()
            self.currentWidth = widgetwidth
            self.currentHeight = widgetheight
            self.image.setPixmap(newpixmap)
    def GetImage(self):
        if self.busy >= 1:
            ShowMessageBox("Please wait for the current image to load.", Warning)
            return
        self.getImageButton.setEnabled(False)
        self.loadImageButton.setEnabled(False)
        self.busy = 1
        self.thread = threading.Thread(target=self.ParseImage)
        self.thread.start()
        register(self.thread.join)
    def Request(self, url, output):
        # Need to use curl because requests module is blocked
        subprocess.call(["curl", "-o", output, url], shell=True)
        if not os.path.exists(output):
            return False
        return True
    def ParseImage(self):
        animal = self.animalChoice.currentText()
        url = animals[animal]
        if url == "":
            url = self.apiDomain.text()
            if url == "":
                self.busy = 3
                return
        else:
            requested = self.Request(url, "temp.json")
            if requested == False:
                self.busy = 4
                return
            url = None
            with open("temp.json", "r") as file:
                url = GetImageUrl(animal, json.load(file))
            if url is None:
                self.busy = 5
                return
        # Escape special characters for curl
        escapes = {
            " ": "%20",
            "&": "^&",
            #"?": "%3F",
            #"#": "%23",
            #"%": "%25"
        }
        for escape in escapes.keys():
            url = url.replace(escape, escapes[escape])
        self.imageext = url.split(".")[-1]
        # If there are any special characters after the extension, remove them
        if "?" in self.imageext:
            self.imageext = self.imageext.split("?")[0]
        if "#" in self.imageext:
            self.imageext = self.imageext.split("#")[0]
        if "%" in self.imageext:
            self.imageext = self.imageext.split("%")[0]
        if "&" in self.imageext:
            self.imageext = self.imageext.split("&")[0]
        if "^" in self.imageext:
            self.imageext = self.imageext.split("^")[0]
        requested = self.Request(url, "temp." + self.imageext)
        if requested == False:
            self.busy = 6
            return
        self.imagepath = "temp." + self.imageext
        self.busy = 2
    def LoadImage(self):
        # Prompt user to select an image
        self.imagepath = QtGui.QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)")[0]
        if self.imagepath == "":
            return
        self.busy = 2
    def Cleanup(self):
        # Delete temp files
        if os.path.exists("temp.json"):
            os.remove("temp.json")
        if os.path.exists("temp." + self.imageext):
            os.remove("temp." + self.imageext)
        if os.path.exists("screenshot.bmp"):
            os.remove("screenshot.bmp")
        self.getImageButton.setEnabled(True)
        if self.animalChoice.currentText() == "Custom":
            self.loadImageButton.setEnabled(True)
        if self.animalChoice.currentText() == "Window":
            self.getImageButton.setEnabled(False)

NoIcon = QtGui.QMessageBox.NoIcon
Question = QtGui.QMessageBox.Question
Information = QtGui.QMessageBox.Information
Warning = QtGui.QMessageBox.Warning
Critical = QtGui.QMessageBox.Critical

def ShowMessageBox(message, icon=Information):
    msgBox = QtGui.QMessageBox()
    msgBox.setText(message)
    msgBox.setIcon(icon)
    title = ProductName
    if icon == Question:
        title = title + ": Question"
    elif icon == Warning:
        title = title + ": Warning"
    elif icon == Critical:
        title = title + ": Error"
    else:
        title = title + ": Information"
    msgBox.setWindowTitle(title)
    msgBox.exec_()

def CreateScriptWindow():
    try:
        scriptWindow = AnimalWindow()
        globals()[InternalName + "_window"] = scriptWindow
        pointer = shiboken.getCppPointer(scriptWindow)
        sfmApp.RegisterTabWindow(InternalName + "_window", ProductName, pointer[0] )
    except Exception as e:
        import traceback
        traceback.print_exc()        
        msgBox = QtGui.QMessageBox()
        msgBox.setText("Error: %s" % e)
        msgBox.exec_()

def DestroyScriptWindow():
    try:
        globalScriptWindow = globals().get(InternalName + "_window")
        if globalScriptWindow is not None:
            globalScriptWindow.close()
            globalScriptWindow.deleteLater()
            globalScriptWindow = None
            globals()[InternalName + "_window"] = None
    except Exception as e:
        import traceback
        traceback.print_exc()        
        msgBox = QtGui.QMessageBox()
        msgBox.setText("Error: %s" % e)
        msgBox.exec_()

try:
    # Create window if it doesn't exist
    globalScriptWindow = globals().get(InternalName + "_window")
    if globalScriptWindow is None:
        CreateScriptWindow()
    else:
        dialog = QtGui.QMessageBox.warning(None, ProductName + ": Error", ProductName + " is already open.\n\nIf you are a developer, click Yes to forcibly open a new instance.\n\nOtherwise, click No to close this message.", QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No)
        if dialog == QtGui.QMessageBox.Yes:
            DestroyScriptWindow()
            CreateScriptWindow()
    try:
        sfmApp.ShowTabWindow(InternalName + "_window")
    except:
        pass
except Exception  as e:
    import traceback
    traceback.print_exc()        
    ShowMessageBox("Error: %s" % e, Critical)

if InternalName + "_ran" not in globals():
    globals()[InternalName + "_ran"] = True
