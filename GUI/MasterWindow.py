from tkinter import BooleanVar, DoubleVar, LabelFrame, Tk,filedialog, Canvas, Toplevel, StringVar, IntVar, Entry, Label, Checkbutton, Button, Entry, Frame, Menu, END, messagebox
from tkinter import ttk #ttk = themed Tkinter for "improved aesthetics and additional widgets"

from PIL import Image
import csv
import copy

#imports (FOLLOW INSTALLATION INSTRUCTIONS PROVIDED IF NECESSARY)
from matplotlib import pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap, to_hex
import promptlib  
from .GridWIndow import GridWindow

from .BaseCanvas import BaseCanvas
#from .PulseCanvas import PulseCanvas
#from .PulseStepCanvas import PulseStepCanvas
#from .PulseCycleCanvas import PulseCycleCanvas
#from .IvCanvas import IvCanvas
from .PulseCanvasGrid import PulseCanvasGrid
from .PulseStepCanvasGrid import PulseStepCanvasGrid
from .PulseCycleCanvasGrid import PulseCycleCanvasGrid
from .IvCanvasGrid import IVCanvasGrid

import os
from threading import Thread


class MasterWindowClass(Tk): #overarching Tkinter window class to hold both frames

    def __init__(self, sendCallback, stopCallback): #create initializing functionality
        super().__init__()
        
        self.sendCallback = sendCallback
        self.stopCallback = stopCallback

        self.cellGrid: GridWindow = None

        self.fileSaveWindow = None
        self.canvas: BaseCanvas = None
        
        self.title("Packaged ReRAM Testing GUI")
        self.geometry("450x700")

        #prevent changing the size of the GUI as well as closing protocols
        self.resizable(True, True)

        #declare the variables that will be shared between widgets
        self.saveFileName = StringVar(self)
        self.saveFileName.set('new_test')
        self.saveDirectory = StringVar(self)
        self.saveDirectory.set(os.path.join(os.getcwd(), 'Data')) #os.getcwd())
        
        self.importFileName = StringVar(self)
        
        self.heatMapSettingWindow = None
        self.cmapColorsStr = StringVar(self)
        self.currentBoundersStr = StringVar(self)
        self.resistanceBoundersStr = StringVar(self)

        self.currBinaryMode = BooleanVar()
        self.currColorMode = BooleanVar()
        self.binaryMode = BooleanVar(self)

        self.binaryMode.set(True)
        self.currBinaryMode.set(True)
        self.currColorMode.set(False)
        

        color = ["#5083B9FF" , "#E2E4E6FF", "#836767FF", "#A3A2A2FF", "#666666FF",  "#3D3E3FFF", "#944B4BFF", "#070707FF", "#940606FF"]
        # self.cmapColors = 'Greys'
        self.cmapColors = 'RdYlGn'
        # self.cmapColors = '#576B80FF , #C0C3C5FF, #836767FF, #7A7A7AFF,  #3D3E3FFF, #944B4BFF, #070707FF, #940606FF'
        self.currentBounders = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 35, 40]
        # self.resistanceBounders = [0, 5, 10, 40, 60, 100]
        # self.resistanceBounders =  [5, 8, 11, 13, 17, 22, 28, 36, 45]
        self.resistanceBounders =  [0,2,4,5,6,7,8,9,10,20,30,40,50,60,70,80,90,100,120,150,180,210]

        self.createModeButtonFrame()

        # === THE ULTIMATE TOUCHSCREEN SCROLLING FIX ===
        # 1. Define a cross-platform scroll function that explicitly controls the canvas viewport
        def directional_scroll(event):
            if event.delta: # Windows / macOS tracking
                self.modeCanvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4: # Linux scroll up (Raspberry Pi touchscreens)
                self.modeCanvas.yview_scroll(-1, "units")
            elif event.num == 5: # Linux scroll down (Raspberry Pi touchscreens)
                self.modeCanvas.yview_scroll(1, "units")

        # 2. Attach the helper function directly to the class structure using "self."
        def apply_scroll_to_all_children(parent_widget):
            parent_widget.bind("<MouseWheel>", directional_scroll)
            parent_widget.bind("<Button-4>", directional_scroll)
            parent_widget.bind("<Button-5>", directional_scroll)
            for child in parent_widget.winfo_children():
                apply_scroll_to_all_children(child)
        
        # Save it to the class instance so other methods can see it
        self.apply_scroll_to_all_children = apply_scroll_to_all_children

        # 3. Bind the main canvas wrapper area
        self.modeCanvas.bind_all("<MouseWheel>", directional_scroll)
        self.modeCanvas.bind_all("<Button-4>", directional_scroll)
        self.modeCanvas.bind_all("<Button-5>", directional_scroll)

        self.initGridWindow()
        self.initMenuBar()

        # make the pulse test canvas the default
        self.createCanvas('pulse_test')



    def print(self, line:str, clear=False, isCommand=False, isDone=False):
        if self.canvas:
            if clear:
                self.canvas.console.delete('0', END)
            if isCommand:
                line = '>>> ' + line
            self.canvas.console.insert(END, line)
            self.canvas.console.insert(END, '>>> ') if isDone else None
            self.canvas.console.see(END)
    
    def clearProgress(self, canvas:BaseCanvas):
        for i in reversed(range(canvas.console.size())):
            item_text = canvas.console.get(i)
            if item_text.startswith(">>> Starting the Threads") or item_text.startswith("Done"):
                break
            if item_text.startswith("Time Elapsed:"):
                canvas.console.delete(i)
                break
            if item_text.startswith("Progress:"):   
                canvas.console.delete(i)
                

    def createModeButtonFrame(self):
        """
        Configures the main responsive canvas area with functioning 
        vertical and horizontal scrollbars.
        """
        # Create a fluid content canvas with no hardcoded pixel limits
        self.modeCanvas = Canvas(self)
        self.modeCanvas.grid(row=0, column=0, sticky='nsew')
        
        # Configure window weights so the main canvas stretches dynamically
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # 1. Vertical Scrollbar (Right Edge)
        modeScrollBarY = ttk.Scrollbar(self, orient='vertical', command=self.modeCanvas.yview)
        modeScrollBarY.grid(row=0, column=1, sticky='ns')
        
        # 2. Horizontal Scrollbar (Bottom Edge)
        modeScrollBarX = ttk.Scrollbar(self, orient='horizontal', command=self.modeCanvas.xview)
        modeScrollBarX.grid(row=1, column=0, sticky='ew')
        
        # Link both scrollbars to the canvas framework
        self.modeCanvas.configure(yscrollcommand=modeScrollBarY.set, xscrollcommand=modeScrollBarX.set)

        # Content frame inside the canvas
        self.ModeCanvasFrame = Frame(self.modeCanvas, bd=2, relief='solid', padx=5)
        self.canvasWindow = self.modeCanvas.create_window((0, 0),
                             window=self.ModeCanvasFrame, anchor="nw")
        
        def update_scroll_region(event):
            # Calculate total bounding box area of elements
            bbox = self.modeCanvas.bbox("all")
            # Set scroll region with a tiny extra padding safety net so things move smoothly
            self.modeCanvas.configure(scrollregion=(bbox[0], bbox[1], bbox[2] + 20, bbox[3] + 20))

        # Continuously monitor inner frame resizing events to unlock scrollbars
        self.ModeCanvasFrame.bind("<Configure>", update_scroll_region)
        
        

    def getCanvas(self) -> BaseCanvas:
        return copy.copy(self.canvas) if self.canvas else None

    def createCanvas(self, canvasType): #function to create the canvas
        # Return if canvas is already created
        if self.canvas and self.canvas.modeState == canvasType:
            return
        
        # First: clear all existing widgets inside the canvas frame
        for child in self.ModeCanvasFrame.winfo_children():
            child.destroy()

        match canvasType:
            case 'pulse_test':
                self.canvas = PulseCanvasGrid(self.ModeCanvasFrame)
                
            case 'pulse_step_test':
                self.canvas = PulseStepCanvasGrid(self.ModeCanvasFrame)   

            case 'pulse_cycle_test':
                self.canvas = PulseCycleCanvasGrid(self.ModeCanvasFrame)

            case 'iv_test':
                #since this frame needs more space to show all the information,
                #reconfigure the frame dimensions
                self.ModeCanvasFrame.config(width = 1000, height = 300)
                
                self.canvas = IVCanvasGrid(self.ModeCanvasFrame)


        # set the submit button command
        self.canvas.saveDirectory = self.saveDirectory
        self.saveFileName = self.canvas.saveFileName
        self.canvas.modeState.set(canvasType)
        self.canvas.submitButton.config(command=self.sendCallback)   
        self.canvas.stopButton.config(command=self.stopCallback)

        # when binaryMode changes, change the canvas's individual binaryMode
        self.binaryMode.trace_add('write', lambda *args:self.canvas.toggleBinaryMode(self.binaryMode.get()))
        # do it once initially in case a picture is already imported when the new canvas is selected
        self.canvas.toggleBinaryMode(self.binaryMode.get())
        self.apply_scroll_to_all_children(self.ModeCanvasFrame)


    def initMenuBar(self):
        """
        Initializes the top menu bar, adding an integrated 'Test Mode' selector 
        to eliminate the need for any on-screen button panels or sidebar spaces.
        """
        self.menuBar = Menu(self)
        
        # ----- File Menu -----
        self.fileMenu = Menu(self.menuBar, tearoff = 0)
        self.fileMenu.add_command(label = 'Import File', command = lambda: self.initImportFileWindow())
        self.fileMenu.add_command(label = 'Export Settings', command = lambda: self.initExportSettings(self))
        self.fileMenu.add_command(label = 'Heatmap Settings', command = lambda: self.initHeatmapSettings())
        self.fileMenu.add_separator()
        self.fileMenu.add_command(label = "Exit", command = lambda: self.destroy())
        self.menuBar.add_cascade(label = "File", menu = self.fileMenu)

        # ----- View Menu -----
        self.viewMenu = Menu(self.menuBar, tearoff=0)
        self.gridViewMenu = Menu(self.viewMenu, tearoff=0)
        self.gridViewMenu.add_command(label="Pixel View", command=lambda:self.cellGrid.setPixelView())
        self.gridViewMenu.add_command(label="Normal View", command=lambda:self.cellGrid.setNormalView())
        self.viewMenu.add_cascade(label="Grid", menu=self.gridViewMenu)
        self.menuBar.add_cascade(label="View", menu=self.viewMenu)

        # ----- INTEGRATED TEST MODE SELECTOR -----
        self.modeMenu = Menu(self.menuBar, tearoff=0)
        self.modeMenu.add_command(label="Pulse Testing", command=lambda: self.createCanvas('pulse_test'))
        self.modeMenu.add_command(label="Potentiation Testing", command=lambda: self.createCanvas('pulse_step_test'))
        self.modeMenu.add_command(label="Pulse Testing - SET/RESET Switch", command=lambda: self.createCanvas('pulse_cycle_test'))
        self.modeMenu.add_command(label="IV Testing", command=lambda: self.createCanvas('iv_test'))
        self.menuBar.add_cascade(label="Test Mode", menu=self.modeMenu)

        # Apply configured menu bar to root window
        self.config(menu = self.menuBar)

    
    def initGridWindow(self):
        # Create the secondary window but keep it hidden initially
        cellGridWindow = Toplevel(self)
        cellGridWindow.withdraw()  # Hide until grid is ready
        cellGridWindow.geometry("800x700")
        cellGridWindow.title('Cell/Device Selection Grid (White = False, Black = True)')
        cellGridWindow.protocol("WM_DELETE_WINDOW", lambda: self.destroy())

        cellGridWindow.columnconfigure(0, weight=1)
        cellGridWindow.rowconfigure(0, weight=1)

        # Show a temporary loading message inside the window
        loading_frame = ttk.Frame(cellGridWindow)
        loading_frame.grid(row=0, column=0, padx=20, pady=20, sticky='nsew')
        loading_frame.columnconfigure(0, weight=1)
        loading_frame.rowconfigure(0, weight=1)

        loading_label = ttk.Label(loading_frame, text="Creating grid... Please wait.")
        loading_label.grid(row=0, column=0, sticky='')  # no sticky = centered

        # Display the window with just the loading message
        cellGridWindow.update()
        cellGridWindow.deiconify()


        def worker():
            # --- Create layout components in background ---
            # Main frame
            cellGridFrame = ttk.Frame(cellGridWindow)

            # Canvas and scrollbars
            cellGridCanvas = Canvas(cellGridFrame, width=800, height=700)
            scrollBarVertY = ttk.Scrollbar(cellGridFrame, orient='vertical', command=cellGridCanvas.yview)
            scrollBarHorizX = ttk.Scrollbar(cellGridFrame, orient='horizontal', command=cellGridCanvas.xview)
            cellGridCanvas.configure(yscrollcommand=scrollBarVertY.set, xscrollcommand=scrollBarHorizX.set)

            # Content frame inside the canvas
            cellGridContentFrame = ttk.Frame(cellGridCanvas)
            cellGridContentFrame.bind("<Configure>", lambda e:
                cellGridCanvas.configure(scrollregion=cellGridCanvas.bbox("all")))
            cellGridCanvas.create_window((0, 0), window=cellGridContentFrame, anchor="nw")

            # Create grid content (may take time)
            self.cellGrid = GridWindow(cellGridContentFrame, self.binaryMode)

            # Once done, update GUI on main thread
            def show_grid():
                if self.cellGrid.finishGrid:
                    # Remove loading label
                    loading_frame.destroy()

                    # Layout full grid window
                    cellGridFrame.grid(row=0, column=0, sticky='nsew')
                    cellGridCanvas.grid(row=0, column=0, sticky='nsew')
                    scrollBarVertY.grid(row=0, column=1, sticky='ns')
                    scrollBarHorizX.grid(row=1, column=0, sticky='ew')

                    # Resize behavior
                    cellGridWindow.columnconfigure(0, weight=1)
                    cellGridWindow.rowconfigure(0, weight=1)
                    cellGridFrame.columnconfigure(0, weight=1)
                    cellGridFrame.rowconfigure(0, weight=1)
                else:
                    self.after(500, show_grid)

            self.after(0, show_grid)

        Thread(target=worker, daemon=True).start()


    def initHeatmapSettings(self):
        if self.heatMapSettingWindow:
            self.heatMapSettingWindow.destroy()

        self.heatMapSettingWindow = Toplevel(self)
        self.heatMapSettingWindow.title('Heatmap Settings')
        self.heatMapSettingWindow.resizable(True, True)

        self.heatMapSettingWindow.columnconfigure(1, weight=1)

        row = 0
        Label(self.heatMapSettingWindow, text="- Use comma to separate multiple values", font=('calibre', 12, 'normal'), anchor='w', fg='gray').grid(row=0, column=0, padx=30, pady=(20, 0), columnspan=4, sticky='ew')
        Label(self.heatMapSettingWindow, text="- Use Standard Color group e.g 'Greens'; 'Oranges'; 'Reds'; 'YlOrBr'; 'YlOrRd'; 'OrRd' or...", font=('calibre', 12, 'normal'), anchor='w', fg='gray').grid(row=1, column=0, padx=30, columnspan=4, sticky='ew')
        Label(self.heatMapSettingWindow, text="- Use Custom Color group list e.g ['red', 'green', 'blue'] or ['#ff0000', '#ffff00', '#00ff00'] ", font=('calibre', 12, 'normal'), anchor='w', fg='gray').grid(row=2, column=0, padx=30, columnspan=4, sticky='ew')
        Label(self.heatMapSettingWindow, text="- see https://matplotlib.org/stable/tutorials/colors/colormaps.html for more info", font=('calibre', 12, 'normal'), anchor='w', fg='gray').grid(row=3, column=0, padx=30, columnspan=4, sticky='ew')

        row += 4
        self.cmapColorsStr.set(' ' + ', '.join(map(str, self.cmapColors))) if isinstance(self.cmapColors, list) else self.cmapColorsStr.set(' ' + self.cmapColors)
        Label(self.heatMapSettingWindow, text='CMap Colors: ', font=('calibre', 12, 'normal')).grid(row=row, padx=(20, 0), pady=(30, 5),column=0, sticky='w')
        Entry(self.heatMapSettingWindow, textvariable=self.cmapColorsStr, font=('calibre', 12, 'normal')).grid(row=row, column=1, columnspan=3, padx=(1, 20), pady=(30, 5), sticky='ew')

        row += 1
        self.currentBoundersStr.set(' ' + ', '.join(map(str, self.currentBounders)))
        self.currentBoundersLabel = Label(self.heatMapSettingWindow, text='Current Boundaries: ', font=('calibre', 12, 'normal'))
        self.currentBoundersLabel.grid(row=row, column=0, padx=(20, 0),  sticky='w')
        Entry(self.heatMapSettingWindow, textvariable=self.currentBoundersStr, font=('calibre', 12, 'normal')).grid(row=row, column=1, columnspan=3, padx=(1, 20), pady=(5, 5), sticky='ew')

        row += 1
        self.resistanceBoundersStr.set(' ' + ', '.join(map(str, self.resistanceBounders)))
        self.resistanceBoundersLabel = Label(self.heatMapSettingWindow, text='Resistance Boundaries: ', font=('calibre', 12, 'normal'))
        self.resistanceBoundersLabel.grid(row=row, column=0, padx=(20, 0),  sticky='w')
        Entry(self.heatMapSettingWindow, textvariable=self.resistanceBoundersStr, font=('calibre', 12, 'normal')).grid(row=row, column=1, columnspan=3, padx=(1, 20), pady=(5, 5), sticky='ew')

        row += 1
        Button(self.heatMapSettingWindow, text='Save Settings', command=self.saveHeatmapSettings, font=('calibre', 12, 'normal')).grid(row=row, column=2, pady=20, sticky='e')
        Button(self.heatMapSettingWindow, text='Close', command=self.heatMapSettingClose, font=('calibre', 12, 'normal')).grid(row=row, column=3, padx=(10, 20), pady=20, sticky='e')

        self.heatMapSettingWindow.protocol("WM_DELETE_WINDOW", lambda:self.heatMapSettingClose())
    
    def heatMapSettingClose(self):
        self.heatMapSettingWindow.destroy()
        self.heatMapSettingWindow = None


    def saveHeatmapSettings(self):
        error = False

        # Reset label colors
        self.currentBoundersLabel.config(fg='black')
        self.resistanceBoundersLabel.config(fg='black')

        raw_str = self.cmapColorsStr.get().strip('[]').strip()

        if ',' in raw_str:
            self.cmapColors = [c.strip() for c in raw_str.split(',')]
        else:
            self.cmapColors = [raw_str]


        # Validate and convert currentBounders
        try:
            self.currentBounders = [int(item.strip()) for item in self.currentBoundersStr.get().strip('[]').strip().split(',')]
        except ValueError:
            self.currentBoundersLabel.config(fg='red')
            error = True

        # Validate and convert resistanceBounders
        try:
            self.resistanceBounders = [int(item.strip()) for item in self.resistanceBoundersStr.get().strip('[]').strip().split(',')]
        except ValueError:
            self.resistanceBoundersLabel.config(fg='red')
            error = True

        if not error:
            self.heatMapSettingWindow.destroy()

    #initializes and opens export setting window
    def initExportSettings(self, master):

        try: #check if already open, call "openFileSaveWindow" if not

            if(self.fileSaveWindow.state() == 'normal'): #if currently open (state = normal means it's open)
                print('already open') #state that it's open already
                self.fileSaveWindow.focus()

        except:
            self.openFileSaveWindow(master) #calls built in "openFileSaveWindow" function


    
    #opens export settings window
    def openFileSaveWindow(self, master):
        # Create the Toplevel window
        self.fileSaveWindow = Toplevel(master)
        self.fileSaveWindow.title('Export Settings')
        self.fileSaveWindow.resizable(True, True)

        # Set default save directory if empty
        if self.saveDirectory.get() == '':
            default_dir = os.path.join(os.getcwd(), 'Exported Data')
            self.saveDirectory.set(default_dir)

        # ----- Grid Layout -----

        # Row 0: Current folder label
        Label(self.fileSaveWindow, text='Current Export Folder:', font=('calibre', 12, 'bold'))\
            .grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 2), sticky='w')

        # Row 1: Change Dir button and directory entry
        self.changeDirectoryButton = Button(self.fileSaveWindow, text='Change Dir',
                                            command=self.chooseExportDirectory, width=10, bg='white')
        self.changeDirectoryButton.grid(row=1, column=0, padx=10, pady=5, sticky='w')

        self.saveDirectoryBox = Entry(self.fileSaveWindow, textvariable=self.saveDirectory,
                                    font=('calibre', 10), bg='white')
        self.saveDirectoryBox.grid(row=1, column=1, columnspan=2, padx=10, pady=5, sticky='ew')

        # Row 2: File name
        Label(self.fileSaveWindow, text='Name of file:', font=('calibre', 10))\
            .grid(row=2, column=0, padx=10, pady=5, sticky='e')

        self.saveFileNameEntry = Entry(self.fileSaveWindow, textvariable=self.saveFileName,
                                    font=('calibre', 10), bg='white')
        self.saveFileNameEntry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')

        Label(self.fileSaveWindow, text='.csv', font=('calibre', 10))\
            .grid(row=2, column=2, padx=5, sticky='w')

        # Row 3: Save button
        self.saveExportButton = Button(self.fileSaveWindow, text='Save',
                                    command=self.saveExportSettings, height=2, width=6, bg='white')
        self.saveExportButton.grid(row=3, column=2, padx=10, pady=10, sticky='e')

        # ---- Configure weight for resizability ----
        self.fileSaveWindow.grid_columnconfigure(0, weight=0)
        self.fileSaveWindow.grid_columnconfigure(1, weight=1)
        self.fileSaveWindow.grid_columnconfigure(2, weight=0)
        self.fileSaveWindow.grid_rowconfigure(1, weight=1)
    #-------------------------------------------------------------------------

    #function that allows the user to change export directory folder
    def chooseExportDirectory(self):

        #select new directory using "promptlib" library
        self.prompter = promptlib.Files()
        self.selectedDirectory = self.prompter.dir()

        #set default
        if(self.selectedDirectory == ''):
            self.selectedDirectory = os.path.join(os.getcwd(), 'Data')

        self.saveDirectoryBox.delete(0, END)
        self.saveDirectoryBox.insert(0, self.selectedDirectory)
        self.fileSaveWindow.attributes('-topmost', True)

    #-------------------------------------------------------------------------

    #saves export settings chosen in fileSaveWindow until changed or reset
    def saveExportSettings(self):
        self.saveFileName.set(self.saveFileNameEntry.get()) 
        self.saveDirectory.set(self.saveDirectoryBox.get())

        self.fileSaveWindow.destroy()   

    
    def initImportFileWindow(self):

        self.importWindow = Toplevel(self.master)
        self.importWindow.title('Import File')
        self.importWindow.resizable(True, False)
        self.importWindow.attributes('-topmost', True) 

        self.importDone = False
        self.currBinaryMode.set(self.binaryMode.get())

        # self.importWindow.grid_columnconfigure(0, weight=0)
        # self.importWindow.grid_columnconfigure(1, weight=1)
        # self.importWindow.grid_columnconfigure(2, weight=0)
        # self.importWindow.grid_rowconfigure(1, weight=1)

        frame = Frame(self.importWindow)
        frame.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')
        self.importWindow.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(2, weight=1)
        
        checkButtonFrame = Frame(frame)
        checkButtonFrame.grid(row=0, column=1, columnspan=3, padx=0, pady=0, sticky='nsew')
        checkButtonFrame.grid_columnconfigure(0, weight=1)
        checkButtonFrame.grid_columnconfigure(2, weight=1)

        checkButtonFrameInner = Frame(checkButtonFrame)
        checkButtonFrameInner.grid(row=0, column=1, padx=0, pady=0, sticky='nsew')

        Checkbutton(checkButtonFrameInner, text='Binary Image (.csv)', variable=self.currBinaryMode).grid(row=0, column=1, padx=(20, 10), columnspan=1, sticky='ew')
        self.currBinaryMode.trace_add('write', lambda *args:self.binaryModeChanged(self.currBinaryMode.get()))

        Checkbutton(checkButtonFrameInner, text='Image', variable=self.currColorMode).grid(row=0, column=2, padx=(10, 0), columnspan=1, sticky='ew')
        self.currColorMode.trace_add('write', lambda *args:self.colorModeChanged(self.currColorMode.get()))


        Label(frame, text='File: ', font=('calibre', 12)).grid(row=4, column=0, padx=(10, 0), pady=5, sticky='ew')
        Entry(frame, textvariable=self.importFileName, font=('calibre', 12)).grid(row=4, column=1, columnspan=3, padx=5, pady=5, sticky='ew')
        Button(frame, text='Browse', command=self.getImageFilePath).grid(row=4, column=4, padx=(5, 10), sticky='w')

        Button(frame, text='Import', command=lambda:self.importFileToGrid(self.cellGrid)).grid(row=5, column=3, padx=0, pady=(15, 10), sticky='e')
        Button(frame, text='Finish', command=self.finishImportFileWindow).grid(row=5, column=4, padx=(5, 10), pady=(15, 10), sticky='e')

        self.importWindow.protocol("WM_DELETE_WINDOW", lambda: self.finishImportFileWindow())


    def binaryModeChanged(self, state):
        if state:
            if self.currColorMode.get():
                self.currColorMode.set(False)        
        else:
            if not self.currColorMode.get():
                self.currColorMode.set(True)


    def colorModeChanged(self, state):
        if state:
            if self.currBinaryMode.get():
                self.currBinaryMode.set(False)
        else:
            if not self.currBinaryMode.get():
                self.currBinaryMode.set(True)


    def finishImportFileWindow(self):
        if self.importDone:
            self.importWindow.destroy()
            return
        
        # Ask the user before closing
        confirm = messagebox.askyesno(
            "Confirm Import",
            "No file has been imported. Are you sure you want to close?"
        )

        if confirm:
            self.importWindow.destroy()
        else:
            return 
        
    def getImageFilePath(self):
        
        self.importWindow.attributes('-topmost', False)
        #get the file to be imported by finding the file path (.csv files ONLY)

        #for the sake of having the correct types be selectable first for
        #the binary .csv files OR the colored images, create a list of corresponding
        #file types applicable to the chosen check box in the "Import File" window
        #NOTE: Since currBinaryMode and currColorMode cannot be set at the same time,
        #checking against one of the booleans is enough to tell which of the two states
        #are set, so currBinaryMode was chosen
        if(self.currBinaryMode.get()): #if selecting a binary image
            filetypes = [("Binary Grid Files (*.csv, *.tsv, *.xls, *.xlsx, *.xlsm)", \
                          "*.csv *.tsv *.xls *.xlsx *.xlsm")]
            
        else: #otherwise, selecting an image file
            filetypes = [("Image Files (*.png, *.jpg, *.jpeg, *.bmp, *.gif, *.tiff, *.webp)", \
                          "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp")]
        
        self.CSVFilePath = filedialog.askopenfilename(title = "Select File", \
                                                filetypes = filetypes)
        self.importWindow.attributes('-topmost', True)

        self.importFileName.set(self.CSVFilePath)

    #initializes and opens import CSV file window
    def importFileToGrid(self, cellGrid:GridWindow):
        
        if not cellGrid.finishGrid:
            self.after(100, lambda: self.importFileToGrid(cellGrid))
            return 
        
        if not self.importFileName.get():
            return

        #extract the binary information of the import .csv file
        importedGrid = []

        filename = self.importFileName.get().strip()
        importedGrid = self.readFile(filename)
        
        #first, reset the grid before adding the logic
        cellGrid.toggle_all(False)

        try:
            if self.currBinaryMode.get():
                
                    #iterate though entire importedGrid using the two FOR loops based on the grid dimensions
                    for row in range(cellGrid.returnRowNum()):
                        for column in range(cellGrid.returnColumnNum()):

                            #if the importedGrid cell has a 1, set the corresponding
                            #cellGrid to pressed
                            if(float(importedGrid[row][column]) >= 0.4):
                                cellGrid.clickedButton(row, column)
                    self.cellGrid.setPixelView()

            else:
                import numpy as np
                self.rangesBorders = np.linspace(0, 1, 256).tolist()
                self.cmap, self.norm = MasterWindowClass.getNormCMap(self.rangesBorders, 'Greys')

                for row in range(cellGrid.returnRowNum()):
                    for col in range(self.cellGrid.returnColumnNum()):
                        cellGrid.grid[row][col].config(bg=self.get_value_color(float(importedGrid[row][col])))
                self.cellGrid.setPixelView()

        except Exception as e:
            print(f"Error: invalid file value: {e}")

        self.binaryMode.set(self.currBinaryMode.get())


        self.cellGrid.importedGrid = importedGrid
        self.cellGrid.setPixelView()
        self.importDone = True

        

        # # - - - - - - - - - - - - - - - - - - - - - - -

        # #now that the Excel data has all been imported, change the boolean/grid logic
        # #of the cellGrid
        # if self.binaryMode.get():
        #     #first, set all of the cells to False to reset the grid before adding the logic
        #     cellGrid.toggle_all(False)

        #     #iterate though entire importedGrid using the two FOR loops based on the grid dimensions
        #     for row in range(cellGrid.returnRowNum()):
        #         for column in range(cellGrid.returnColumnNum()):

        #             #if the importedGrid cell has a 1, set the corresponding
        #             #cellGrid to pressed
        #             if(int(importedGrid[row][column]) == 1):
        #                 cellGrid.clickedButton(row, column)
        #     self.cellGrid.setPixelView()
        # else:
        #     self.rangesValues = [  7 ,  12,  20,  30,  40,  50,   60, 80, 100 ]
        #     self.rangesBorders = np.linspace(0, 1, 256).tolist()

        #     cellGrid.toggle_all(False)
        #     self.cmap, self.norm = MasterWindowClass.getNormCMap(self.rangesBorders, 'Greys')
        #     for row in range(cellGrid.returnRowNum()):
        #         for col in range(self.cellGrid.returnColumnNum()):
        #             cellGrid.grid[row][col].config(bg=self.get_value_color(importedGrid[row][col]))
        #     self.cellGrid.setPixelView()

    def readFile(self, fileName):
        ext = os.path.splitext(fileName)[1].lower()  # Get file extension in lowercase
        importedGrid = []
        if ext in ('.xls', '.xlsx', '.xlsm', '.csv', '.tsv'):
            print("This is an Excel or CSV file.")

            #open the file in a read format as a means of getting the data
            with open(self.importFileName.get(), mode = 'r', encoding = 'utf-8-sig') as readFile:

                readerData = csv.reader(readFile) #use csv.reader to get the file data

                #NOTE: this will change with the CellGrid dimensions
                startRow = 0
                startColumn = 0

                #since this is a 2D grid, enumerate through the rows and columns of individual cells
                for column, row in enumerate(readerData):
                    
                    if(column >= startRow + self.cellGrid.returnRowNum()): #break enumeration logic, will loop otherwise
                        break

                    #get full row with all (maxColumn) # of columns
                    currentRow = row[startColumn:startColumn + self.cellGrid.returnColumnNum()]

                    #save the currentRow information before going to the next column in importedGrid list
                    importedGrid.append([float(val) for val in currentRow])

                return importedGrid
        elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'):
            import numpy as np

            k = 7        # number of clusters ------------------------------------------------------
             
            # -------- Step 1: Load and resize --------
            image, clusters = self.getClusteredImage(fileName, k)
            
            print(clusters)
            # Convert each row of pixels to a list and append to importedGrid
            # Convert to NumPy array
            arr = np.array(image, dtype=np.float32)

            # Invert: 255 becomes 0, 0 becomes 255
            arr = 255 - arr

            # Normalize to 0.0–1.0
            arr /= 255.0

            # Convert back to list of lists if you still need that format
            importedGrid = arr.tolist() 

            # Save the importedGrid to a CSV file
            output_filename = fileName.split('.')[0] + '.csv'
            with open(output_filename, mode='w', newline='') as file:
                writer = csv.writer(file)
                for row in importedGrid:
                    writer.writerow(row) 

            return importedGrid
        
        else:
            print("Unsupported file type.")
            return None
        

    def getClusteredImage(self, fileName, k):
        import cv2
        import numpy as np
        from sklearn.cluster import KMeans

        resize_dim = (64, 64)
        image = cv2.imread(fileName)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, resize_dim)

        # -------- Step 2: Flatten for clustering --------
        pixels = image.reshape(-1, 3)

        # -------- Step 3: Apply K-Means --------
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(pixels)
        colors = kmeans.cluster_centers_.astype(np.uint8)

        # -------- Step 4: Build clustered image --------
        clustered_pixels = colors[labels]
        clustered_img = clustered_pixels.reshape(image.shape)

        # Convert clustered image to grayscale
        gray_clustered = cv2.cvtColor(clustered_img, cv2.COLOR_RGB2GRAY)

        # -------- Step 5: Min/Max grayscale values per cluster --------
        # Flatten grayscale image to match labels (4096,)
        gray_flat = gray_clustered.flatten()

        clusters = []
        for cluster_id in range(k):
            cluster_pixels = gray_flat[labels == cluster_id]
            if len(cluster_pixels) > 0:
                clusters.append(int(cluster_pixels.max()))
        clusters.sort(reverse=True)

        for i, cluster in enumerate(clusters.copy()):
            clusters[i] = (255 - cluster)/255
        return gray_clustered, clusters
    

    def get_value_color(self, value):
        rgba = self.cmap(self.norm(value))  # tuple like (r, g, b, a)
        rgb = rgba[:3]  # drop alpha
        return to_hex(rgb)  # convert to "#RRGGBB"
    

    @staticmethod      
    def getNormCMap(boundaries, colorMap='RdYlGn'):

        n_colors = len(boundaries) - 1  # You need one color per interval
        if isinstance(colorMap, str):
            # --- Define or generate a colormap with enough colors ---
            # Option 1: use a built-in colormap and truncate it
            # if colorMap == 'Greys':
            #     from matplotlib import cm
            #     from matplotlib.colors import LinearSegmentedColormap
            #     import numpy as np
            #     greyCmap = cm.get_cmap("Greys")
            #     cmap = LinearSegmentedColormap.from_list(
            #         "Greys_no_white",
            #         greyCmap(np.linspace(0, 1, 256))  # Cut off last 10% (white end)
            #     )
            # else:
            cmap = plt.get_cmap(colorMap, n_colors)  # Discrete viridis with n_colors shades
            
        elif isinstance(colorMap, list):
            if len(colorMap) == 1:
                cmap = plt.get_cmap(colorMap[0], n_colors)
            else:
                # Option 2: define your own (example)
                cmap = ListedColormap(colorMap)
    

        # --- Define the norm based on the boundaries ---
        norm = BoundaryNorm(boundaries, ncolors=n_colors, clip=True)

        return cmap, norm
    #-------------------------------------------------------------------------

    #opens import CSV file for grid binary window
    def openCSVFileWindow(self, master):

        #create the fileSaveWindow and assign dimensions
        self.fileSaveWindow = Toplevel(master)
        self.fileSaveWindow.title('Export Settings')
        self.fileSaveWindowCanvas = Canvas(self.fileSaveWindow, width = 450, height = 130)

        #separate window in N number of equally spaced columns/rows
        self.fileSaveWindowCanvas.grid(rowspan = 20, columnspan = 4)

        self.fileSaveWindow.resizable(False, False)


    #-------------------------------------------------------------------------
