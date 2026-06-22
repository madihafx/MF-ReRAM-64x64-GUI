import math
from Util.InputOutputKernel import InOutKernel
from Util.SerialPort import SerialPort
from Util.CsvManager import CsvManager

import re #for IV Test for regular expression operations
import time
import threading
import random
import pandas as pd
import copy
import time
from math import ceil
from GUI import BaseCanvas
import matplotlib.pyplot as plt
import numpy as np
import os

class InOutManger(InOutKernel):
    def __init__(self, serialPort:SerialPort, debug = False, sudoTest = False):
        super().__init__(debug)
        self.cmd = serialPort

        self.csvMgr = CsvManager(debug)
        self.debug = debug
        self.sudoTest = sudoTest

        self.initSleepTime = 0

        # Data to be updated and plotted in the main Thread
        # Updating the GUI is not thread safe, so we need to do it in the main thread
        self.plotDataDict:dict[dict[str, float]] = {}
        self.plotDataDictHeatMap:dict[dict[str, float]] = {}
        self.plotDataLock = threading.Lock()
        self.plotDataHeatMapLock = threading.Lock()

        self.inputTarget = None
        self.outputTarget = None
        self.executeTarget = None
        self.finishTarget = None
    

    def init(self, canvas:BaseCanvas):
        self.canvas = canvas
        self.cycles = canvas.cycleNumber.get()
        self.readVoltages = (canvas.formSetReadVoltage.get() * 1000, canvas.resetReadVoltage.get() * 1000)
        if canvas.applyToAllDevices.get():
            self.setRead2Delay = [canvas.formSetTime.get() + canvas.delayPeriodTime.get()  + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]
            self.setResetRead2Delay = [canvas.formSetTime.get() + canvas.delayPeriodTime.get()  + 100, canvas.resetTime.get() + canvas.delayPeriodTime.get() + 100, 
                                                     canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]
        self.expectedDelay = self.getExpectedDelay(canvas)

        self.plotDataDict = {}
        self.plotDataDictHeatMap = {}
        self.resetResults()

        # CSV file trackers
        self.csvRows = 0
        self.csvSheet = 0
        # info lists for step testing and range verification
        self.csvInfo = []

        if not self.expectedDelay:
            raise Exception("Invalid Settings: Time and Delay settings...")
        
        self.saveIntermediateData = canvas.csvControlVariable.get() or canvas.createSavePlots.get()
        if self.saveIntermediateData or self.canvas.createHeatMap.get(): # only creates a directory if the user wants a CSV file or plots
            self.csvMgr.setDataDirectory(self.canvas.saveDirectory.get(), self.canvas.saveFileName.get())
            print(f"Data Directory: {self.csvMgr.folderDirectory}") if self.debug else None

        match canvas.modeState.get():
            
            case 'pulse_test':

                if canvas.utilizeCurResRange.get():
                    self.maxCycles = canvas.pulseTestRangeCycleCount.get()

                    self.read2ByteList          = canvas.getRead2ByteList()
                    self.read2Delay = [canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]

                    self.setRead2ByteList       = canvas.getSetRead2ByteList()
                    self.setRead2Delay = [canvas.formSetTime.get() + canvas.delayPeriodTime.get()  + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]

                    self.resetByteList     = canvas.getResetByteList() 
                    self.resetDelay = [canvas.resetTime.get() + canvas.delayPeriodTime.get() + 100] # us

                    self.setResetRead2ByteList  = canvas.getSetResetRead2ByteList()
                    self.setResetRead2Delay = [canvas.formSetTime.get() + canvas.delayPeriodTime.get()  + 100, canvas.resetTime.get() + canvas.delayPeriodTime.get() + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]
                    
                    
                    # When getting the MaxCurr and MinCurr, we must calculate the maxCurrent using the minRange
                    if canvas.applyToAllDevices.get():
                        self.deviceStat = None # use the stat from the devices grid.
                        if canvas.toggledOhmsLawUnit.get() != 'uA':
                            self.hrsMaxCurr = canvas.resetReadVoltage.get() *1000 / canvas.hrsRangeMin.get() if canvas.hrsRangeMin.get() != 0 else np.finfo(np.float64).max # max current
                            self.hrsMinCurr = canvas.resetReadVoltage.get() *1000 / canvas.hrsRangeMax.get() if canvas.hrsRangeMax.get() != 0 else np.finfo(np.float64).max
                            self.lrsMaxCurr = canvas.resetReadVoltage.get() *1000 / canvas.lrsRangeMin.get() if canvas.lrsRangeMin.get() != 0 else np.finfo(np.float64).max
                            self.lrsMinCurr = canvas.resetReadVoltage.get() *1000 / canvas.lrsRangeMax.get() if canvas.lrsRangeMax.get() != 0 else np.finfo(np.float64).max
                        else:
                            self.hrsMinCurr = canvas.hrsRangeMin.get()
                            self.hrsMaxCurr = canvas.hrsRangeMax.get()
                            self.lrsMinCurr = canvas.lrsRangeMin.get()
                            self.lrsMaxCurr = canvas.lrsRangeMax.get()

                    else:
                        if canvas.lrsRangeMax.get() > 0 and canvas.hrsRangeMax.get() > 0:
                            raise Exception("Invalid Settings: LRS and HRS ranges cannot be set at the same time...")
                        if canvas.hrsRangeMax.get() > 0:
                            if canvas.toggledOhmsLawUnit.get() != 'uA': #kOhm
                                self.hrsMaxCurr = canvas.resetReadVoltage.get() * 1000 / canvas.hrsRangeMin.get() if canvas.hrsRangeMin.get() != 0 else np.finfo(np.float64).max
                                self.hrsMinCurr = canvas.resetReadVoltage.get() * 1000 / canvas.hrsRangeMax.get() if canvas.hrsRangeMax.get() != 0 else np.finfo(np.float64).max 
                            else: #uA
                                self.hrsMinCurr = canvas.hrsRangeMin.get()
                                self.hrsMaxCurr = canvas.hrsRangeMax.get()
                            self.deviceStat = True

                        elif canvas.lrsRangeMax.get() > 0:
                            if canvas.toggledOhmsLawUnit.get() != 'uA': #kOhm
                                self.lrsMaxCurr = canvas.resetReadVoltage.get() * 1000 / canvas.lrsRangeMin.get() if canvas.lrsRangeMin.get() != 0 else np.finfo(np.float16).max
                                self.lrsMinCurr = canvas.resetReadVoltage.get() * 1000 / canvas.lrsRangeMax.get() if canvas.lrsRangeMax.get() != 0 else np.finfo(np.float16).max 
                            else: #uA
                                self.lrsMinCurr = canvas.lrsRangeMin.get()
                                self.lrsMaxCurr = canvas.lrsRangeMax.get()
                            self.deviceStat = False
                        else:
                            print("Invalid Range Settings...")
                            return

                    self.initNewRow     = self.init_rangeVerify_newRow
                    self.inputTarget    = self.processInputPulseRangeTest
                    self.outputTarget   = self.processOutputPulseRangeTest
                    self.executeTarget  = self.createRangePulseTestPLots
                    self.finishTarget   = self.createCSV
                    
                elif canvas.kernelProcessingTest.get():
                    self.kernelMatrix = [[float(num) for num in row.replace('[','').replace(']','').split(',')]
                                            for row in canvas.kernelMatStr.get().strip().strip('[]').split(';')]
                    
                    self.kernelSize = len(self.kernelMatrix)
                    self.gridSize = 64
                    if self.kernelSize != len(self.kernelMatrix[0]):
                        raise Exception("Invalid Kernel Size...")
                    
                    if self.kernelSize % 2 != 0:
                        self.getNeighbors = self.get_neighbors_odd
                    else:
                        self.getNeighbors = self.get_neighbors_even
    
                    self.kernel = [num*1000 for row in self.kernelMatrix for num in row]
                    self.read2Delay = [canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]

                    self.initNewRow     = self.init_newRow
                    self.inputTarget    = self.processKernelProcessingInput
                    self.outputTarget   = self.processKernelTestOutput
                    self.executeTarget  = self.createPulseTestPlots
                    self.finishTarget   = self.createCSV

                elif canvas.writeImage.get() and not canvas.binaryMode.get():
                    self.baseGateVoltage = canvas.gateVoltageMax.get() * 1000
                    self.minGateVoltage = canvas.gateVoltageMin.get() * 1000
                    self.gateVoltageStep = canvas.gateStepVoltage.get() * 1000
                    self.maxCycles = canvas.verifyCycles.get()
                    self.levelTolerance = canvas.levelTolerance.get() / 100
                    self.baseResetVoltage = canvas.resetVoltageMin.get() * 1000
                    self.maxResetVoltage = canvas.resetVoltageMax.get() * 1000

                    self.read2ByteList = canvas.getRead2ByteList()
                    self.read2Delay = [canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]

                    self.resetByteList     = canvas.getResetByteList() 
                    self.resetDelay = [canvas.resetTime.get() + canvas.delayPeriodTime.get() + 100] # us

                    self.setResetRead2Delay = [canvas.formSetTime.get() + canvas.delayPeriodTime.get()  + 100, canvas.resetTime.get() + canvas.delayPeriodTime.get() + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]
                    self.setRead2Delay      =  [canvas.formSetTime.get() + canvas.delayPeriodTime.get()  + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]

                    if canvas.toggledOhmsLawUnit.get() == 'uA':
                        self.rangeThreshold = canvas.gateRangeThreshold.get()
                    else:
                        self.rangeThreshold = canvas.resetReadVoltage.get() * 1000 / canvas.gateRangeThreshold.get() if canvas.gateRangeThreshold.get() != 0 else np.finfo(np.float16).max
                        
                    self.initNewRow     = self.init_levelVerify_newRow
                    self.inputTarget    = self.processWriteImageInput
                    self.outputTarget   = self.processOutputPulseRangeTest
                    self.executeTarget  = self.createRangePulseTestPLots
                    self.finishTarget   = self.createCSV
                    
                else:
                    
                    if canvas.applyToAllDevices.get():
                        self.inputTarget = self.processAllDevicesInputPulseTest
                        self.initNewRow = self.init_AllDevices_newRow
                        
                    else:
                        if canvas.retentionTest.get():
                            self.inputTarget = self.processRetentionInputPulseTest
                            self.expectedDelay = [canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]
                            self.initNewRow = self.init_newRow
                        elif canvas.gateRangeTest.get():
                            self.expectedDelay =  [canvas.formSetTime.get() + canvas.delayPeriodTime.get()  + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]
                            self.inputTarget = self.processInputPulseTest
                            self.initNewRow = self.init_gateVoltage_newRow
                        else:
                            self.inputTarget = self.processInputPulseTest
                            self.initNewRow = self.init_newRow
                        

                    self.outputTarget = self.processOutputPulseTest
                    self.executeTarget = self.createPulseTestPlots
                    self.finishTarget = self.createCSV

            #-------------------------------------------------------------------------------------------

            case 'pulse_step_test': #for pulse step test run

                #set all target threads to their expected thread functions

                #NOTE: Since the only options are related to creating .csv and scatter plot files,
                #there is no need for multiple IF/ELIF/ELSE statements for all other Pulse Test options
                
                #NOTE: error checking for canvas inputs is handled in the MainApp program's "isValidSetting" function

                if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, use FORM/SET time delay
                    self.expectedDelay =  [canvas.formSetTime.get() + canvas.delayPeriodTime.get() + 100, canvas.formSetReadTime.get() + canvas.delayPeriodTime.get() + 100]
                else: #otherwise, RESET, use RESET time delay
                    self.expectedDelay =  [canvas.resetTime.get() + canvas.delayPeriodTime.get() + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]

                self.inputTarget    = self.processInputPulseStepTest #calls processInputPulseStepTest function within this program
                self.initNewRow     = self.init_newRow #calls init_newRow function within this program
                self.outputTarget   = self.processOutputPulseTest #calls processOutputPulseTest function within this program
                self.executeTarget  = self.createPulseTestPlots #calls createPulseTestPlots function within this program
                self.finishTarget   = self.createCSV #calls createCSV function within this program

            #-------------------------------------------------------------------------------------------

            case 'pulse_cycle_test': #for Pulse SET/RESET Switch Test run

                #set all target threads to their expected thread functions

                #NOTE: Since the only options are related to creating .csv, scatter plot files and inverting SET/RESET order,
                #there is no need for multiple IF/ELIF/ELSE statements for all other Pulse Test options

                #NOTE: Since this approach will do a SET input and RESET input PER CYCLE, the expected time delay will utilize
                #both expected delay formats in some form, so the expected delay logic will not be messed with

                self.inputTarget    = self.processInputPulseCycleTest #calls processInputPulseCycleTest function within this program
                self.initNewRow     = self.init_newRow #calls init_newRow function within this program
                self.outputTarget   = self.processOutputPulseTest #calls processOutputPulseTest function within this program
                self.executeTarget  = self.createPulseTestPlots #calls createPulseTestPlots function within this program
                self.finishTarget   = self.createCSV #calls createCSV function within this program

            #-------------------------------------------------------------------------------------------

            case 'iv_test': #for IV Test run

                #set all target threads to their expected thread functions

                print('IV Test in progress')

                #NOTE: Since the only options are related to creating .csv and scatter plot files,
                #there is no need for multiple IF/ELIF/ELSE statements for all other Pulse Test options
                
                #NOTE: error checking for canvas inputs is handled in the MainApp program's "isValidSetting" function

                if(self.canvas.IvTestState.get() == 'FORM' or self.canvas.IvTestState.get() == 'SET'): #if FORM or SET, use FORM/SET time delay
                    self.expectedDelay =  [canvas.formSetTime.get() + canvas.delayPeriodTime.get() + 100, canvas.formSetReadTime.get() + canvas.delayPeriodTime.get() + 100]
                elif(self.canvas.IvTestState.get() == 'RESET'): #if RESET, use RESET time delay
                    self.expectedDelay =  [canvas.resetTime.get() + canvas.delayPeriodTime.get() + 100, canvas.resetReadTime.get() + canvas.delayPeriodTime.get() + 100]
                #otherwise, unique IV mode state, which will use the full expectedDelay already created during the "init" function call using the "getExpectedDelay" function
                            
                self.inputTarget    = self.processInputIVTest #calls processInputIVTest function within this program
                self.initNewRow     = self.init_newRow #calls init_newRow function within this program
                self.outputTarget   = self.processOutputIVTest #calls processOutputIVTest function within this program (uses getValuesIV function instead of getValues)
                self.executeTarget  = self.createPulseTestPlots #calls createPulseTestPlots function within this program
                self.finishTarget   = self.createCSV #calls createCSV function within this program

        print(f"New Delays: {self.expectedDelay}") if self.debug else None  
        time.sleep(1)
            
    #------------------------------------------------------------------------------------------- 
    
    def getData(self, unit, factor=1):
        """
        Converts the data to the specified unit with an optional scaling factor.

        Args:
            unit (str): The target unit for conversion ('uA' or 'kOhm').
            factor (float): A scaling factor to apply during conversion. e.g 1e6 to get current in A instead of uA.

        Returns:
            pd.DataFrame: The converted data.
        """
        data = self.getResults()  

        if unit == 'uA':
            return data

        def convert_column(data:pd.DataFrame, col_name, voltage, factor):
            """
            Converts the specified column using the given voltage and scaling factor.
            """
            if col_name in data.columns:
                current = data[col_name]
                zero_mask = current == 0
                # Avoid division by zero, use maximum float value instead
                data[col_name] = np.round(np.where(
                    zero_mask,
                    np.finfo(np.float16).max,
                    (voltage / current) * factor)
                , 2) # round to 2 decimal places

        try:
            convert_column(data, 'Read1', self.readVoltages[0], factor)
            convert_column(data, 'Read2', self.readVoltages[1], factor)

            return data

        except ZeroDivisionError:
            print("Warning: Division by zero in voltage during unit conversion.")
            self.errorEvent.set()
            self.stopEvent.set()
            return data  # Return current state even after error

        except Exception as e:
            print(f"Error: {e}")
            self.errorEvent.set()
            self.stopEvent.set()
            return data

    #function to be called by "UpdatePlots" in the "MainApp.py" file for
    #generating SCATTER PLOTS ONLY
    def getPlotData(self) ->dict[dict[str, float]]: 
        with self.plotDataLock:
            return copy.deepcopy(self.plotDataDict) if self.plotDataDict else pd.DataFrame()

    #function to be called by "UpdatePlots" in the "MainApp.py" file for
    #generating HEAT MAPS ONLY
    def getPlotDataHeatMap(self) ->dict[dict[str, float]]: 
        with self.plotDataHeatMapLock:
            return copy.deepcopy(self.plotDataDictHeatMap) if self.plotDataDictHeatMap else pd.DataFrame()

# --------------------------------------------------------------------------------------------------
                                # INPUT TARGET FUNCTIONS
# ----------------------------------------------------------------------------------------------------
    def processInputPulseTest(self, input:list):
        
        lines = None
        try:
            # if FORM mode selected, only send input command if device is not yet formed
            if(self.canvas.formSetStateString.get() == 'FORM'):
                # create byte list for reading before seonding the FORM command
                formRead = copy.deepcopy(input)
                # find proper delay time and voltages
                offset = 100 # us
                formReadDelay = []
                delayTime = self.canvas.delayPeriodTime.get()
                if (self.canvas.formSetReadVoltage.get() != 0) and (self.canvas.formSetReadTime.get() != 0):
                    formReadDelay.append(self.canvas.formSetReadTime.get() + delayTime + offset)
                    formRead[3] = self.canvas.getRead1ByteList()
                    mode = 'formSetRead'
                else: # there is no read 1, so must use read 2
                    formReadDelay.append(self.canvas.resetReadTime.get() + delayTime + offset)
                    formRead[3] = self.canvas.getRead2ByteList()
                    mode = 'resetRead'

                formRead[3][22] = input[1] # col
                formRead[3][23] = input[0] # row
                # set cycles to 1 for both formRead[3] and input[3], since the loop will handle the cycles
                formRead[3][24], formRead[3][25] = input[3][24], input[3][25] = self.canvas.twoByteComboSplit(1)

                cycle = 1
                while cycle < self.cycles+1:
                    # first, send just the read command
                    print(formRead[3])
                    self.cmd.resetBuffer()
                    self.cmd.write(bytearray(formRead[3])) # formRead[3] is the byteList
                    time.sleep(self.initSleepTime)
                    lines = self.readLines(formReadDelay, [])

                    if lines and (len(lines) == len(formReadDelay)):
                        output = formRead.copy()
                        output[2] = cycle
                        output[3] = lines
                        reads = self.getValues(lines)
                        # checks if the device has been formed (resistance <= 100000 based on uA)
                        maxResistance = 100000
                        if (mode == 'formSetRead'): #using read 1
                            if (reads['Read1']['Value'] >= self.canvas.resetReadVoltage.get() / maxResistance * 1000000):
                                self.outputQueue.put(output.copy()) # use this read as the output
                                self.progress += self.cycles - cycle + 1 # progress as if this device has gone through all cycles
                                return  # and do not form again
                        else: # using read 2
                            if (reads['Read2']['Value'] >= self.canvas.resetReadVoltage.get() / maxResistance * 1000000):
                                self.outputQueue.put(output.copy()) # use this read as the output
                                self.progress += self.cycles - cycle + 1 # progress as if this device has gone through all cycles
                                return  # and do not form again
                        print(f"Unformed, reads: {reads}")
                    else:
                        print("No output received: ", formRead)
                        self.stopEvent.set()

                    # now send form command if the device isn't formed yet
                    print(input[3])
                    self.cmd.resetBuffer()
                    self.cmd.write(bytearray(input[3])) # input[3] is the byteList
                    time.sleep(self.initSleepTime)
                    lines = self.readLines(self.expectedDelay, [])

                    if lines and (len(lines) == len(self.expectedDelay)):
                        output = input.copy()
                        output[2] = cycle
                        output[3] = lines
                        reads = self.getValues(lines)
                        self.outputQueue.put(output.copy())
                        self.progress += 1
                    else:
                        print("No output received: ", input)
                        self.stopEvent.set()
                    cycle += 1

            # previously created logic applied only if SET mode is chosen
            else:
                # Send the input command
                print(input[3])
                self.cmd.resetBuffer()
                self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                cycle = 1
                while cycle < self.cycles+1:
                    # This time is critical for receiving the correct data.
                    # I assume it is the time the board needs to send the first output.
                    # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                    time.sleep(self.initSleepTime)
                    lines = self.readLines(self.expectedDelay, [])

                    if lines and (len(lines) == len(self.expectedDelay)):
                        output = input.copy()
                        output[2] = cycle
                        output[3] = lines
                        self.outputQueue.put(output.copy())
                        self.progress += 1
                    else:
                        print("No output received: ", input)
                        self.stopEvent.set()
                    cycle +=1

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {lines}")
            self.stopEvent.set()
            self.errorEvent.set()

    #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    #function that will read the board information while cycling
    #through the input byte list while changing the voltage information
    #based on the rising/falling voltage step order

    #input list format (as defined in the InputOutputKernel "addInput" function):
    #[row, column, current_cycle (preset to 1 by default), byteList]

    #NOTE: recall that BaseCanvas has been defined in the init function as "canvas"
    def processInputPulseStepTest(self, input: list):

        lines = None

        #read from the command until '\n' is received 
        try:  
            #first read while setting the row and column information
            input[3][22] = input[1] # col
            input[3][23] = input[0] # row

            #ALSO, each SerialPort write will require the byte array to be for ONE CYCLE,
            #as a WHILE loop further down will address the number of cycles instead of the byteList
            input[3][24] = 0 #cycle number, MSB
            input[3][25] = 1 #cycle number, LSB

            #NOTE: cmd as defined by Quotayba is the SerialPort program file
            self.cmd.resetBuffer() #clear the input buffer of the serial port

            # - - - - - - - - - - - - - - - - - - - - - - - - - -

            #pull the necessary information from canvas (which would be using the
            #PulseStepCanvasGrid in this case) for determining the step logic
            #Required Information:
            #maximum step voltage as determined by chosenStepVoltage (maxFormSetVoltage or maxResetVoltage)
            #minimum step voltage as determined by chosenStepVoltage (formSetVoltage or resetVoltage)
            #number of steps (stepNumber)
            # and must run pre-test operations, set-read-reset-read if SET, set-read-reset-read-set-read if RESET
            if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, use FORM/SET voltage
                maxStepVoltage = int(self.canvas.maxFormSetVoltage.get() * 1000) # max voltage for step logic
                minStepVoltage = int(self.canvas.formSetVoltage.get() * 1000)

                # find proper delay time for the pre-test operation
                offset = 100 # us
                delayList = []
                delayTime = self.canvas.delayPeriodTime.get()
                # SET and RESET time is fixed to 100 us, since 1 us is often used for steps but is too little for pre-test
                if maxStepVoltage != 0:
                    delayList.append(100 + delayTime + offset)
                if self.canvas.formSetReadVoltage.get() != 0:
                    delayList.append(self.canvas.formSetReadTime.get() + delayTime + offset)
                if self.canvas.maxResetVoltage.get() != 0:
                    delayList.append(100 + delayTime + offset)
                if self.canvas.resetReadVoltage.get() != 0:
                    delayList.append(self.canvas.resetReadTime.get() + delayTime + offset)

                preTest = copy.deepcopy(input)
                # use max step voltage as set voltage and maxResetVoltage as reset voltage
                preTest[3][4], preTest[3][5] = self.canvas.twoByteComboSplit(maxStepVoltage)
                preTest[3][14], preTest[3][15] = self.canvas.twoByteComboSplit(self.canvas.maxResetVoltage.get() * 1000)
                preTest[3][26], preTest[3][27] = self.canvas.twoByteComboSplit(0) # steps
                # SET and RESET time is fixed to 100 us, since 1 us is often used for steps but is too little for pre-test
                preTest[3][6], preTest[3][7] = preTest[3][16], preTest[3][17] = self.canvas.twoByteComboSplit(100)
                # run pre-testing set, read, reset, read
                print(preTest[3])
                self.cmd.write(bytearray(preTest[3])) # preTest[3] is the byteList
                time.sleep(self.initSleepTime)
                lines = self.readLines(delayList, [])

                if lines and (len(lines) == len(delayList)):
                    output = preTest.copy()
                    output[2] = 0
                    output[3] = lines
                    # blank step, voltage, and SET/RESET column if needed
                    self.csvInfo.append('')
                    if self.canvas.incrementVoltage.get():
                        self.csvInfo.append('')
                    if self.canvas.stepVoltageDirection.get() == 'Rise then Fall':
                        self.csvInfo.append('')
                    self.outputQueue.put(output.copy())
                else:
                    print("No output received: ", preTest)
                    self.stopEvent.set()
                    
                # remove reset and read 2 bits for step operations and fix delay time
                input[3][14], input[3][15] = input[3][18], input[3][19] = self.canvas.twoByteComboSplit(0)
                self.expectedDelay = []
                if maxStepVoltage != 0:
                    self.expectedDelay.append(self.canvas.formSetTime.get() + delayTime + offset)
                if self.canvas.formSetReadVoltage.get() != 0:
                    self.expectedDelay.append(self.canvas.formSetReadTime.get() + delayTime + offset)
            else: #otherwise, RESET, use RESET voltage
                maxStepVoltage = int(self.canvas.maxResetVoltage.get() * 1000) # max voltage for step logic
                minStepVoltage = int(self.canvas.resetVoltage.get() * 1000)
                
                # find proper delay time for the pre-test operation
                offset = 100 # us
                delayList = []
                delayTime = self.canvas.delayPeriodTime.get()
                if self.canvas.maxFormSetVoltage.get() != 0:
                    delayList.append(100 + delayTime + offset)
                if self.canvas.formSetReadVoltage.get() != 0:
                    delayList.append(self.canvas.formSetReadTime.get() + delayTime + offset)
                if maxStepVoltage != 0:
                    delayList.append(100 + delayTime + offset)
                if self.canvas.resetReadVoltage.get() != 0:
                    delayList.append(self.canvas.resetReadTime.get() + delayTime + offset)

                preTest = copy.deepcopy(input)
                # use max step voltage as reset voltage and maxFormSetVoltage as set voltage
                preTest[3][14], preTest[3][15] = self.canvas.twoByteComboSplit(maxStepVoltage)
                preTest[3][4], preTest[3][5] = self.canvas.twoByteComboSplit(self.canvas.maxFormSetVoltage.get() * 1000)
                preTest[3][26], preTest[3][27] = self.canvas.twoByteComboSplit(0) # steps
                # SET and RESET time is fixed to 100 us, since 1 us is often used for steps but is too little for pre-test
                preTest[3][6], preTest[3][7] = preTest[3][16], preTest[3][17] = self.canvas.twoByteComboSplit(100)
                # run pre-testing set, read, reset, read
                print(preTest[3])
                self.cmd.write(bytearray(preTest[3])) # pretest[3] is the byteList
                time.sleep(self.initSleepTime)
                lines = self.readLines(delayList, [])

                if lines and (len(lines) == len(delayList)):
                    output = preTest.copy()
                    output[2] = 0
                    output[3] = lines
                    # blank step, voltage, and SET/RESET column if needed
                    self.csvInfo.append('')
                    if self.canvas.incrementVoltage.get():
                        self.csvInfo.append('')
                    if self.canvas.stepVoltageDirection.get() == 'Rise then Fall':
                        self.csvInfo.append('')
                    self.outputQueue.put(output.copy())
                else:
                    print("No output received: ", preTest)
                    self.stopEvent.set()

                # run pre-testing set, read, find proper delay time for the pre-test operation
                delayList = []
                if self.canvas.maxFormSetVoltage.get() != 0:
                    delayList.append(100 + delayTime + offset)
                if self.canvas.formSetReadVoltage.get() != 0:
                    delayList.append(self.canvas.formSetReadTime.get() + delayTime + offset)

                preTest[3][14], preTest[3][15] = preTest[3][18], preTest[3][19] = self.canvas.twoByteComboSplit(0)

                print(preTest[3])
                self.cmd.write(bytearray(preTest[3])) # preTest[3] is the byteList
                time.sleep(self.initSleepTime)
                lines = self.readLines(delayList, [])

                if lines and (len(lines) == len(delayList)):
                    output = preTest.copy()
                    output[2] = 0
                    output[3] = lines
                    # blank step, voltage, and SET/RESET column if needed
                    self.csvInfo.append('')
                    if self.canvas.incrementVoltage.get():
                        self.csvInfo.append('')
                    if self.canvas.stepVoltageDirection.get() == 'Rise then Fall':
                        self.csvInfo.append('')
                    self.outputQueue.put(output.copy())
                else:
                    print("No output received: ", preTest)
                    self.stopEvent.set()

                # remove set and read 1 bits for step operations and fix delay time
                input[3][4], input[3][5] = input[3][10], input[3][11] = self.canvas.twoByteComboSplit(0)
                self.expectedDelay = []
                if maxStepVoltage != 0:
                    self.expectedDelay.append(self.canvas.resetTime.get() + delayTime + offset)
                if self.canvas.resetReadVoltage.get() != 0:
                    self.expectedDelay.append(self.canvas.resetReadTime.get() + delayTime + offset)


            #calculate the step voltage to be incremented/decremented (based on stepVoltageDirection)
            #per step (max and min difference / number of steps)
            stepVoltage = abs(maxStepVoltage - minStepVoltage) / self.canvas.stepNumber.get()

            # - - - - - - - - - - - - - - - - - - - - - - - - - -

            # if incrementing voltage is not selected
            if not self.canvas.incrementVoltage.get():
                # number of cycles sent is actually the step number,
                # since the cycle number tells how many times to do all the steps
                input[3][24], input[3][25] = self.canvas.twoByteComboSplit(self.canvas.stepNumber.get()) # cycles
                input[3][26], input[3][27] = self.canvas.twoByteComboSplit(0) # steps

                cycle = 1
                while cycle < self.cycles+1:
                    if (self.canvas.stepVoltageDirection.get() != 'Rise then Fall'):
                        # Send the input command
                        print(input[3])
                        self.cmd.resetBuffer()
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                        step = 1
                        while step < self.canvas.stepNumber.get()+1:
                            # This time is critical for receiving the correct data.
                            # I assume it is the time the board needs to send the first output.
                            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                            time.sleep(self.initSleepTime)
                            lines = self.readLines(self.expectedDelay, [])

                            if lines and (len(lines) == len(self.expectedDelay)):
                                output = input.copy()
                                output[2] = cycle
                                output[3] = lines
                                self.csvInfo.append(step)
                                self.outputQueue.put(output.copy())
                                self.progress += 1
                            else:
                                print("No output received: ", input)
                                self.stopEvent.set()
                            step += 1

                    else:
                        # first run
                        if(self.canvas.chosenStepVoltage.get() == 'RESET'):
                            setOrReset = 'R'
                            # fix delay time
                            offset = 100 # us
                            self.expectedDelay = []
                            delayTime = self.canvas.delayPeriodTime.get()
                            if self.canvas.resetVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.resetTime.get() + delayTime + offset)
                            if self.canvas.resetReadVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.resetReadTime.get() + delayTime + offset)
                            # change read used (read 1 -> 0, read 2 -> read 2 voltage)
                            input[3][10], input[3][11] = self.canvas.twoByteComboSplit(0)
                            input[3][18], input[3][19] = self.canvas.twoByteComboSplit(self.canvas.resetReadVoltage.get() * 1000)
                            # put in correct SET and RESET voltages
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(self.canvas.resetVoltage.get() * 1000)
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(0) # SET voltage goes to 0
                        else:
                            setOrReset = 'S'
                            # fix delay time
                            offset = 100 # us
                            self.expectedDelay = []
                            delayTime = self.canvas.delayPeriodTime.get()
                            if self.canvas.formSetVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.formSetTime.get() + delayTime + offset)
                            if self.canvas.formSetReadVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.formSetReadTime.get() + delayTime + offset)
                            # change read used (read 2 -> 0, read 1 -> read 1)
                            input[3][18], input[3][19] = self.canvas.twoByteComboSplit(0)
                            input[3][10], input[3][11] = self.canvas.twoByteComboSplit(self.canvas.formSetReadVoltage.get() * 1000)
                            # put in correct SET and RESET voltages
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(self.canvas.formSetVoltage.get() * 1000)
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(0) # RESET voltage goes to 0

                        # Send the input command
                        print(input[3])
                        self.cmd.resetBuffer()
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                        step = 1
                        while step < self.canvas.stepNumber.get()+1:
                            # This time is critical for receiving the correct data.
                            # I assume it is the time the board needs to send the first output.
                            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                            time.sleep(self.initSleepTime)
                            lines = self.readLines(self.expectedDelay, [])

                            if lines and (len(lines) == len(self.expectedDelay)):
                                output = input.copy()
                                output[2] = cycle
                                output[3] = lines
                                self.csvInfo.append(setOrReset)
                                self.csvInfo.append(step)
                                self.outputQueue.put(output.copy())
                                self.progress += 1
                            else:
                                print("No output received: ", input)
                                self.stopEvent.set()
                            step += 1

                        # delay 0.5s before starting second run
                        time.sleep(0.5)

                        # - - - - - - - - - - - - - - - - - -

                        # second run
                        if(self.canvas.chosenStepVoltage.get() == 'SET'):
                            setOrReset = 'R'
                            # fix delay time
                            offset = 100 # us
                            self.expectedDelay = []
                            delayTime = self.canvas.delayPeriodTime.get()
                            if self.canvas.resetVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.resetTime.get() + delayTime + offset)
                            if self.canvas.resetReadVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.resetReadTime.get() + delayTime + offset)
                            # change read used (read 1 -> 0, read 2 -> read 2 voltage)
                            input[3][10], input[3][11] = self.canvas.twoByteComboSplit(0)
                            input[3][18], input[3][19] = self.canvas.twoByteComboSplit(self.canvas.resetReadVoltage.get() * 1000)
                            # put in correct SET and RESET voltages
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(self.canvas.resetVoltage.get() * 1000)
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(0) # SET voltage goes to 0
                        else:
                            setOrReset = 'S'
                            # fix delay time
                            offset = 100 # us
                            self.expectedDelay = []
                            delayTime = self.canvas.delayPeriodTime.get()
                            if self.canvas.formSetVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.formSetTime.get() + delayTime + offset)
                            if self.canvas.formSetReadVoltage.get() != 0:
                                self.expectedDelay.append(self.canvas.formSetReadTime.get() + delayTime + offset)
                            # change read used (read 2 -> 0, read 1 -> read 1)
                            input[3][18], input[3][19] = self.canvas.twoByteComboSplit(0)
                            input[3][10], input[3][11] = self.canvas.twoByteComboSplit(self.canvas.formSetReadVoltage.get() * 1000)
                            # put in correct SET and RESET voltages
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(self.canvas.formSetVoltage.get() * 1000)
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(0) # RESET voltage goes to 0

                        # Send the input command
                        print(input[3])
                        self.cmd.resetBuffer()
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                        step = 1
                        while step < self.canvas.stepNumber.get()+1:
                            # This time is critical for receiving the correct data.
                            # I assume it is the time the board needs to send the first output.
                            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                            time.sleep(self.initSleepTime)
                            lines = self.readLines(self.expectedDelay, [])

                            if lines and (len(lines) == len(self.expectedDelay)):
                                output = input.copy()
                                output[2] = cycle
                                output[3] = lines
                                self.csvInfo.append(setOrReset)
                                self.csvInfo.append(step)
                                self.outputQueue.put(output.copy())
                                self.progress += 1
                            else:
                                print("No output received: ", input)
                                self.stopEvent.set()
                            step += 1

                    cycle += 1

                return # don't do the rest of this method after finishing
            
            # - - - - - - - - - - - - - - - - - - - - - - - - - -

            # if incrementing voltage is selected, do the step voltage process below
            cycle = 1
            while cycle < self.cycles + 1: #process through all the cycles
                input[3][26], input[3][27] = self.canvas.twoByteComboSplit(0) # steps
                #depending on the chosen stepVoltageDirection, use another WHILE loop
                #to cycle through the incrementing/decrementing step voltages to be changed
                if(self.canvas.stepVoltageDirection.get() == 'Rising'): #if Rising option, increment step voltage

                    currentStepVoltage = minStepVoltage #+ stepVoltage # commented out to apply min voltage as well

                    #initialize the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                    #next WHILE loop iteration
                    #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                    #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                    if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, change FORM/SET voltage
                        input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                    else: #otherwise, RESET, change RESET voltage
                        input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                    
                    step = 0
                    while(currentStepVoltage <= maxStepVoltage): #while still incrementing up to the maxStepVoltage

                        print(input[3])
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList
                        # - - - - - - - - - - - - - - - - - -

                        #perform the expected time delays and call the built in "readLines" function
                        #to extract the necessary information using Quotayba's established logic below

                        # This time is critical for receiving the correct data.
                        # I assume it is the time the board needs to send the first output.
                        # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                        time.sleep(self.initSleepTime)
                        lines = self.readLines(self.expectedDelay, [])
                                
                        if lines and (len(lines) == len(self.expectedDelay)):
                            output = input.copy()
                            output[2] = cycle
                            output[3] = lines
                            self.csvInfo.append(step)
                            self.csvInfo.append(int(currentStepVoltage))
                            self.outputQueue.put(output.copy())
                            self.progress += 1
                        else:
                            print("No output received: ", input)
                            self.stopEvent.set()

                        # - - - - - - - - - - - - - - - - - -

                        currentStepVoltage += stepVoltage #increment currentStepVoltage by stepVoltage for next WHILE loop cycle

                        #change the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                        #next WHILE loop iteration
                        #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                        #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                        if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, change FORM/SET voltage
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        else: #otherwise, RESET, change RESET voltage
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        step += 1
                        
                elif(self.canvas.stepVoltageDirection.get() == 'Falling'): #if Falling option, decrement step voltage

                    currentStepVoltage = maxStepVoltage #- stepVoltage # commented out to apply max voltage as well;
                    # initialize the currentStepVoltage to the max before decrementing

                    #initialize the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                    #next WHILE loop iteration
                    #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                    #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                    if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, change FORM/SET voltage
                        input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                    else: #otherwise, RESET, change RESET voltage
                        input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                    
                    step = 0
                    while(currentStepVoltage >= minStepVoltage): #while still decrementing down to the minStepVoltage

                        print(input[3])
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                        # - - - - - - - - - - - - - - - - - -

                        #perform the expected time delays and call the built in "readLines" function
                        #to extract the necessary information using Quotayba's established logic below

                        # This time is critical for receiving the correct data.
                        # I assume it is the time the board needs to send the first output.
                        # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                        time.sleep(self.initSleepTime)
                        lines = self.readLines(self.expectedDelay, [])
                                
                        if lines and (len(lines) == len(self.expectedDelay)):
                            output = input.copy()
                            output[2] = cycle
                            output[3] = lines
                            self.csvInfo.append(step)
                            self.csvInfo.append(int(currentStepVoltage))
                            self.outputQueue.put(output.copy())
                            self.progress += 1
                        else:
                            print("No output received: ", input)
                            self.stopEvent.set()

                        # - - - - - - - - - - - - - - - - - -

                        currentStepVoltage -= stepVoltage #decrement currentStepVoltage by stepVoltage for next WHILE loop cycle

                        #change the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                        #next WHILE loop iteration
                        #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                        #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                        if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, change FORM/SET voltage
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        else: #otherwise, RESET, change RESET voltage
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        step += 1

                else: #otherwise, "Rise then Fall" option, perform either rising SET and then rising RESET or
                    # rising RESET and then rising SET in EVERY CYCLE, depending on which option is selected
                    # SET mode chosen -> rising SET followed by rising RESET
                    # RESET mode chosen -> rising RESET followed by rising SET

                    # FIRST RISING OPERATION
                    # ensure that max and min voltages are correct if this isn't the 1st cycle
                    # and switch which read is used
                    if(self.canvas.chosenStepVoltage.get() == 'RESET'):
                        setOrReset = 'R'
                        maxStepVoltage = int(self.canvas.maxResetVoltage.get() * 1000)
                        minStepVoltage = int(self.canvas.resetVoltage.get() * 1000)
                        # fix delay time
                        offset = 100 # us
                        self.expectedDelay = []
                        delayTime = self.canvas.delayPeriodTime.get()
                        if maxStepVoltage != 0:
                            self.expectedDelay.append(self.canvas.resetTime.get() + delayTime + offset)
                        if self.canvas.resetReadVoltage.get() != 0:
                            self.expectedDelay.append(self.canvas.resetReadTime.get() + delayTime + offset)
                        # change read used (read 1 -> 0, read 2 -> read 2 voltage)
                        input[3][10], input[3][11] = self.canvas.twoByteComboSplit(0)
                        input[3][18], input[3][19] = self.canvas.twoByteComboSplit(self.canvas.resetReadVoltage.get() * 1000)
                    else:
                        setOrReset = 'S'
                        maxStepVoltage = int(self.canvas.maxFormSetVoltage.get() * 1000)
                        minStepVoltage = int(self.canvas.formSetVoltage.get() * 1000)
                        # fix delay time
                        offset = 100 # us
                        self.expectedDelay = []
                        delayTime = self.canvas.delayPeriodTime.get()
                        if maxStepVoltage != 0:
                            self.expectedDelay.append(self.canvas.formSetTime.get() + delayTime + offset)
                        if self.canvas.formSetReadVoltage.get() != 0:
                            self.expectedDelay.append(self.canvas.formSetReadTime.get() + delayTime + offset)
                        # change read used (read 2 -> 0, read 1 -> read 1)
                        input[3][18], input[3][19] = self.canvas.twoByteComboSplit(0)
                        input[3][10], input[3][11] = self.canvas.twoByteComboSplit(self.canvas.formSetReadVoltage.get() * 1000)
                        #calculate the step voltage to be incremented/decremented
                        #per step (max and min difference / number of steps)
                    
                    stepVoltage = abs(maxStepVoltage - minStepVoltage) / self.canvas.stepNumber.get()

                    currentStepVoltage = minStepVoltage #+ stepVoltage # commented out to apply min voltage as well

                    #initialize the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                    #next WHILE loop iteration
                    #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                    #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                    if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, change FORM/SET voltage
                        input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        input[3][14], input[3][15] = self.canvas.twoByteComboSplit(0) # RESET voltage goes to 0
                    else: #otherwise, RESET, change RESET voltage
                        input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        input[3][4], input[3][5] = self.canvas.twoByteComboSplit(0) # SET voltage goes to 0
                    
                    step = 0
                    while(currentStepVoltage <= maxStepVoltage): #while still incrementing up to the maxStepVoltage

                        print(input[3])
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                        # - - - - - - - - - - - - - - - - - -

                        #perform the expected time delays and call the built in "readLines" function
                        #to extract the necessary information using Quotayba's established logic below

                        # This time is critical for receiving the correct data.
                        # I assume it is the time the board needs to send the first output.
                        # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                        time.sleep(self.initSleepTime)
                        lines = self.readLines(self.expectedDelay, [])

                        if lines and (len(lines) == len(self.expectedDelay)):
                            output = input.copy()
                            output[2] = cycle
                            output[3] = lines
                            self.csvInfo.append(setOrReset)
                            self.csvInfo.append(step)
                            self.csvInfo.append(int(currentStepVoltage))
                            self.outputQueue.put(output.copy())
                            self.progress += 1
                        else:
                            print("No output received: ", input)
                            self.stopEvent.set()

                        # - - - - - - - - - - - - - - - - - -

                        currentStepVoltage += stepVoltage #increment currentStepVoltage by stepVoltage for next WHILE loop cycle

                        #change the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                        #next WHILE loop iteration
                        #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                        #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                        if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, change FORM/SET voltage
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        else: #otherwise, RESET, change RESET voltage
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        step += 1

                    # delay 0.5s before starting second rising operation
                    time.sleep(0.5)
                    # - - - - - - - - - - - - - - - - - - - - - - - - - -

                    # SECOND RISING OPERATION
                    # switch max and min step voltages to the opposite of what they were in the first rising operation
                    # and switch which read is used
                    if(self.canvas.chosenStepVoltage.get() == 'SET'):
                        setOrReset = 'R'
                        maxStepVoltage = int(self.canvas.maxResetVoltage.get() * 1000)
                        minStepVoltage = int(self.canvas.resetVoltage.get() * 1000)
                        # fix delay time
                        offset = 100 # us
                        self.expectedDelay = []
                        delayTime = self.canvas.delayPeriodTime.get()
                        if maxStepVoltage != 0:
                            self.expectedDelay.append(self.canvas.resetTime.get() + delayTime + offset)
                        if self.canvas.resetReadVoltage.get() != 0:
                            self.expectedDelay.append(self.canvas.resetReadTime.get() + delayTime + offset)
                        # change read used (read 1 -> 0, read 2 -> read 2 voltage)
                        input[3][10], input[3][11] = self.canvas.twoByteComboSplit(0)
                        input[3][18], input[3][19] = self.canvas.twoByteComboSplit(self.canvas.resetReadVoltage.get() * 1000)
                    else:
                        setOrReset = 'S'
                        maxStepVoltage = int(self.canvas.maxFormSetVoltage.get() * 1000)
                        minStepVoltage = int(self.canvas.formSetVoltage.get() * 1000)
                        # fix delay time
                        offset = 100 # us
                        self.expectedDelay = []
                        delayTime = self.canvas.delayPeriodTime.get()
                        if maxStepVoltage != 0:
                            self.expectedDelay.append(self.canvas.formSetTime.get() + delayTime + offset)
                        if self.canvas.formSetReadVoltage.get() != 0:
                            self.expectedDelay.append(self.canvas.formSetReadTime.get() + delayTime + offset)
                        # change read used (read 2 -> 0, read 1 -> read 1)
                        input[3][18], input[3][19] = self.canvas.twoByteComboSplit(0)
                        input[3][10], input[3][11] = self.canvas.twoByteComboSplit(self.canvas.formSetReadVoltage.get() * 1000)
                    #calculate the step voltage to be incremented/decremented
                    #per step (max and min difference / number of steps)
                    stepVoltage = abs(maxStepVoltage - minStepVoltage) / self.canvas.stepNumber.get()

                    currentStepVoltage = minStepVoltage

                    #initialize the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                    #next WHILE loop iteration
                    #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                    #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                    if(self.canvas.chosenStepVoltage.get() == 'RESET'): #if RESET, change FORM/SET voltage
                        input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        input[3][14], input[3][15] = self.canvas.twoByteComboSplit(0) # RESET voltage goes to 0
                    else: #otherwise, SET, change RESET voltage
                        input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        input[3][4], input[3][5] = self.canvas.twoByteComboSplit(0) # SET voltage goes to 0
                    
                    step = 0
                    while(currentStepVoltage <= maxStepVoltage): #while still incrementing up to the maxStepVoltage

                        print(input[3])
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                        # - - - - - - - - - - - - - - - - - -

                        #perform the expected time delays and call the built in "readLines" function
                        #to extract the necessary information using Quotayba's established logic below

                        # This time is critical for receiving the correct data.
                        # I assume it is the time the board needs to send the first output.
                        # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                        time.sleep(self.initSleepTime)
                        lines = self.readLines(self.expectedDelay, [])
                                
                        if lines and (len(lines) == len(self.expectedDelay)):
                            output = input.copy()
                            output[2] = cycle
                            output[3] = lines
                            self.csvInfo.append(setOrReset)
                            self.csvInfo.append(step)
                            self.csvInfo.append(int(currentStepVoltage))
                            self.outputQueue.put(output.copy())
                            self.progress += 1
                        else:
                            print("No output received: ", input)
                            self.stopEvent.set()

                        # - - - - - - - - - - - - - - - - - -

                        currentStepVoltage += stepVoltage #increment currentStepVoltage by stepVoltage for next WHILE loop cycle

                        #change the voltage chosen by chosenStepVoltage to have the value of the new currentStepVoltage for the
                        #next WHILE loop iteration
                        #NOTE: input[3] is the byteList, and the variables at indices 2 and 3 are the formSetVoltageBytes while
                        #indices 12 and 13 are the resetVoltageBytes respectively (which one to change chosen by chosenStepVoltage)
                        if(self.canvas.chosenStepVoltage.get() == 'RESET'): #if RESET, change FORM/SET voltage
                            input[3][4], input[3][5] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        else: #otherwise, SET, change RESET voltage
                            input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentStepVoltage))
                        step += 1

                cycle += 1 #increment to the next cycle

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {lines}")
            self.stopEvent.set()
            self.errorEvent.set()

    #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    #function that will read the board information while performing SET then RESET
    #(or the opposite order if the BaseCanvas invertIVStates boolean is set) Pulse
    #Tests per cycle

    #input list format (as defined in the InputOutputKernel "addInput" function):
    #[row, column, current_cycle (preset to 1 by default), byteList]

    #NOTE: recall that BaseCanvas has been defined in the init function as "canvas"
    def processInputPulseCycleTest(self, input: list):

        lines = None

        #read from the command until '\n' is received 
        try:  
            #first read while setting the row and column information
            input[3][22] = input[1] # col
            input[3][23] = input[0] # row

            #ALSO, each SerialPort write will require the byte array to be for ONE CYCLE,
            #as a WHILE loop further down will address the number of cycles instead of the byteList
            input[3][24] = 0 #cycle number, MSB
            input[3][25] = 1 #cycle number, LSB

            #to avoid recursion errors while working with the inputted list while also changing
            #some of the bytes within said list, copies of the inputted list are made to have
            #them be saved as independent lists
            firstState = copy.deepcopy(input)
            secondState = copy.deepcopy(input)

            #NOTE: cmd as defined by Quotayba is the SerialPort program file
            self.cmd.resetBuffer() #clear the input buffer of the serial port

            # - - - - - - - - - - - - - - - - - - - - - - - - - -

            #decide to write and read the byte information based on an established
            #SET/RESET order

            if(self.canvas.invertIVStates.get()): #if the states are INVERTED, do RESET THEN SET sequences
                
                #set the first state's byte sequence (firstState[3]) to its RESET ONLY equivalent, with
                #the RESET gate voltage being the chosen gate voltage
                #i.e. set all SET related VOLTAGES to 0V
                firstState[3][4], firstState[3][5] = self.canvas.twoByteComboSplit(0) #FORM/SET voltage
                firstState[3][10], firstState[3][11] = self.canvas.twoByteComboSplit(0) #FORM/SET READ voltage
                firstState[3][2], firstState[3][3] = self.canvas.twoByteComboSplit(self.canvas.gateCycleVoltage.get() * 1000) #gate voltage

                firstStateDelay = [self.canvas.resetTime.get() + self.canvas.delayPeriodTime.get() + 100, \
                                        self.canvas.resetReadTime.get() + self.canvas.delayPeriodTime.get() + 100]

                #set the second state's byte sequence (secondState[3]) to its SET ONLY equivalent, with
                #the SET gate voltage being the chosen gate voltage
                secondState[3][14], secondState[3][15] = self.canvas.twoByteComboSplit(0) #RESET voltage
                secondState[3][18], secondState[3][19] = self.canvas.twoByteComboSplit(0) #RESET READ voltage
                secondState[3][2], secondState[3][3] = self.canvas.twoByteComboSplit(self.canvas.gateVoltage.get() * 1000) #gate voltage

                secondStateDelay = [self.canvas.formSetTime.get() + self.canvas.delayPeriodTime.get() + 100, \
                                        self.canvas.formSetReadTime.get() + self.canvas.delayPeriodTime.get() + 100]

            else: #otherwise, default SET THEN RESET order
                
                #set the first state's byte sequence (firstState[3]) to its SET ONLY equivalent, with
                #the SET gate voltage being the chosen gate voltage
                #i.e. set all RESET related VOLTAGES to 0V
                firstState[3][14], firstState[3][15] = self.canvas.twoByteComboSplit(0) #RESET voltage
                firstState[3][18], firstState[3][19] = self.canvas.twoByteComboSplit(0) #RESET READ voltage
                firstState[3][2], firstState[3][3] = self.canvas.twoByteComboSplit(self.canvas.gateVoltage.get() * 1000) #gate voltage

                firstStateDelay = [self.canvas.formSetTime.get() + self.canvas.delayPeriodTime.get() + 100, \
                                        self.canvas.formSetReadTime.get() + self.canvas.delayPeriodTime.get() + 100]

                #set the second state's byte sequence (secondState[3]) to its RESET ONLY equivalent, with
                #the RESET gate voltage being the chosen gate voltage
                secondState[3][4], secondState[3][5] = self.canvas.twoByteComboSplit(0) #FORM/SET voltage
                secondState[3][10], secondState[3][11] = self.canvas.twoByteComboSplit(0) #FORM/SET READ voltage
                secondState[3][2], secondState[3][3] = self.canvas.twoByteComboSplit(self.canvas.gateCycleVoltage.get() * 1000) #gate voltage

                secondStateDelay = [self.canvas.resetTime.get() + self.canvas.delayPeriodTime.get() + 100, \
                                        self.canvas.resetReadTime.get() + self.canvas.delayPeriodTime.get() + 100]

            cycle = 1
            while cycle < self.cycles + 1: #process through all the cycles

                # send the first state's byte list first
                print(firstState[3])
                self.cmd.write(bytearray(firstState[3])) # firstState[3] is the byteList

                # - - - - - - - - - - - - - - - - - -

                #perform the expected time delays and call the built in "readLines" function
                #to extract the necessary information using Quotayba's established logic below

                # This time is critical for receiving the correct data.
                # I assume it is the time the board needs to send the first output.
                # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                time.sleep(self.initSleepTime)
                lines = self.readLines(firstStateDelay, [])
                            
                if lines and (len(lines) == len(firstStateDelay)):
                    output = firstState.copy()
                    output[2] = cycle
                    output[3] = lines
                    self.outputQueue.put(output.copy())
                    self.progress += 1
                else:
                    print("No output received: ", firstState)
                    self.stopEvent.set()

                # - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

                # send the second state's byte list second
                print(secondState[3])
                self.cmd.write(bytearray(secondState[3])) # input[3] is the byteList

                # - - - - - - - - - - - - - - - - - -

                #perform the expected time delays and call the built in "readLines" function
                #to extract the necessary information using Quotayba's established logic below

                # This time is critical for receiving the correct data.
                # I assume it is the time the board needs to send the first output.
                # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                time.sleep(self.initSleepTime)
                lines = self.readLines(secondStateDelay, [])
                        
                if lines and (len(lines) == len(secondStateDelay)):
                    output = secondState.copy()
                    output[2] = cycle
                    output[3] = lines
                    self.outputQueue.put(output.copy())
                    self.progress += 1
                else:
                    print("No output received: ", secondState)
                    self.stopEvent.set()
                
                cycle += 1 #increment to the next cycle

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {lines}")
            self.stopEvent.set()
            self.errorEvent.set()

    #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    #function for handling the unique FORM/SET/RESET/IV modes (last one being both
    #SET and RESET in a changeable order) with the unique board output information
    #using the 1.1 IV Test mode output logic, with all modes performing rising THEN
    #falling

    #input list format (as defined in the InputOutputKernel "addInput" function):
    #[row, column, current_cycle (preset to 1 by default), byteList]

    #NOTE: 1.1 IV Test output format (with each line be printed PER STEP)
    ##(when rising) RISING-Read1 V = # mV ; I = # uA
    #(when falling) FALLING-Read1 V = # mV ; I = # uA

    #NOTE: Unlike the Step Voltage logic, the IV mode processes the step logic within
    #the board outputs directly, so loops to address this behavior are not necessary

    #NOTE: With the exception of the behavior to be changed within this function, the
    #FORM, SET and RESET IV state default values have already been set within the IvCanvasGrid,
    #so setting any additional values to 0 are not necessary

    #NOTE: Upon testing with various time delays, it was found that the data read into the program
    #manages to get two steps EVERY TIME, so the number of steps cycled through in the WHILE loop is
    #just the step number
    def processInputIVTest(self, input:list):

        lines = None

        #read from the command until '\n' is received 
        try:  
            #first read while setting the row and column information
            input[3][22] = input[1] # col
            input[3][23] = input[0] # row

            #ALSO, each SerialPort write will require the byte array to be for ONE CYCLE,
            #as a WHILE loop further down will address the number of cycles instead of the byteList
            input[3][24] = 0 #cycle number, MSB
            input[3][25] = 1 #cycle number, LSB

            #NOTE: cmd as defined by Quotayba is the SerialPort program file
            self.cmd.resetBuffer() #clear the input buffer of the serial port

            # - - - - - - - - - - - - - - - - - - - - - - - - - -

            #decide to write and read the byte information based on an established
            #SET/RESET order AND/OR the selected IV Test mode

            if(self.canvas.IvTestState.get() == 'IV'): #if the unique IV state mode that will peform both SET and RESET (order changeable)

                #to avoid recursion errors while working with the inputted list while also changing
                #some of the bytes within said list, copies of the inputted list are made to have
                #them be saved as independent lists
                SETInputCopy = copy.deepcopy(input)
                RESETInputCopy = copy.deepcopy(input)

                #set the SETInputCopy byte sequence to REMOVE ALL RESET READ ONLY byte equivalents first, with
                #the SET gate voltage being the chosen gate voltage
                #i.e. set all RESET related VOLTAGES to 0V and TIMES to 0s
                SETInputCopy[3][18], SETInputCopy[3][19] = self.canvas.twoByteComboSplit(0) #RESET READ voltage
                SETInputCopy[3][20], SETInputCopy[3][21] = self.canvas.twoByteComboSplit(0) #RESET READ time
                SETInputCopy[3][2], SETInputCopy[3][3] = self.canvas.twoByteComboSplit(self.canvas.gateVoltage.get() * 1000) #SET gate voltage

                #set the RESETInputCopy byte sequence to REMOVE ALL SET READ ONLY byte equivalents first, with
                #the RESET gate voltage being the chosen gate voltage
                #i.e. set all SET related VOLTAGES to 0V and TIMES to 0s
                RESETInputCopy[3][10], RESETInputCopy[3][11] = self.canvas.twoByteComboSplit(0) #RESET READ voltage
                RESETInputCopy[3][12], RESETInputCopy[3][13] = self.canvas.twoByteComboSplit(0) #RESET READ time
                RESETInputCopy[3][2], RESETInputCopy[3][3] = self.canvas.twoByteComboSplit(self.canvas.gateCycleVoltage.get() * 1000) #RESET gate voltage

                #save the expectedDelays for each input byte list
                expectedDelaySET = [self.canvas.formSetTime.get() + self.canvas.delayPeriodTime.get() + 100, \
                                    self.canvas.formSetReadTime.get() + self.canvas.delayPeriodTime.get() + 100]
                expectedDelayRESET = [self.canvas.resetTime.get() + self.canvas.delayPeriodTime.get() + 100, \
                                      self.canvas.resetReadTime.get() + self.canvas.delayPeriodTime.get() + 100]

                # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

                #perform the WHILE loops for the cycle logic here to avoid checking the IvTestState IF statements every cycle
                #for performance purposes

                #NOTE: While visually drawn out, the following format below of having multiple step WHILE loops with the
                #cmd.write before each said step WHILE loop is for avoid getting a "maximum recursion depth exceeded" error
                
                cycle = 1
                while cycle < self.cycles + 1: #process through all the cycles

                    if(self.canvas.invertIVStates.get()): #if the states are INVERTED, do RESET THEN SET sequences

                        #RESET first
                        self.cmd.write(bytearray(RESETInputCopy[3]))
                        
                        steps = 1
                        while steps < self.canvas.stepNumber.get() + 1:

                            #perform the expected time delays and call the built in "readLines" function
                            #to extract the necessary information using Quotayba's established logic below

                            # This time is critical for receiving the correct data.
                            # I assume it is the time the board needs to send the first output.
                            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                            time.sleep(self.initSleepTime)
                            lines = self.readLines(expectedDelayRESET, [])
                                    
                            if lines and (len(lines) == len(expectedDelayRESET)):
                                output = RESETInputCopy.copy()
                                output[2] = cycle
                                output[3] = lines
                                self.outputQueue.put(output.copy())
                                self.progress += 1
                            else:
                                print("No output received: ", RESETInputCopy)
                                self.stopEvent.set()
                            steps += 1


                        # - - - - - - - - - - - - - - - - - -

                        #now SET
                        self.cmd.write(bytearray(SETInputCopy[3]))

                        steps = 1
                        while steps < self.canvas.stepNumber.get() + 1:

                            #perform the expected time delays and call the built in "readLines" function
                            #to extract the necessary information using Quotayba's established logic below

                            # This time is critical for receiving the correct data.
                            # I assume it is the time the board needs to send the first output.
                            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                            time.sleep(self.initSleepTime)
                            lines = self.readLines(expectedDelaySET, [])
                                    
                            if lines and (len(lines) == len(expectedDelaySET)):
                                output = SETInputCopy.copy()
                                output[2] = cycle
                                output[3] = lines
                                self.outputQueue.put(output.copy())
                                self.progress += 1
                            else:
                                print("No output received: ", SETInputCopy)
                                self.stopEvent.set()
                            steps += 1
                            
                    else: #otherwise, default SET then RESET order
                        
                        #SET first
                        self.cmd.write(bytearray(SETInputCopy[3]))
                        
                        steps = 1
                        while steps < self.canvas.stepNumber.get() + 1:

                            #perform the expected time delays and call the built in "readLines" function
                            #to extract the necessary information using Quotayba's established logic below

                            # This time is critical for receiving the correct data.
                            # I assume it is the time the board needs to send the first output.
                            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                            time.sleep(self.initSleepTime)
                            lines = self.readLines(expectedDelaySET, [])
                                    
                            if lines and (len(lines) == len(expectedDelaySET)):
                                output = SETInputCopy.copy()
                                output[2] = cycle
                                output[3] = lines
                                self.outputQueue.put(output.copy())
                                self.progress += 1
                            else:
                                print("No output received: ", SETInputCopy)
                                self.stopEvent.set()
                            steps += 1


                        # - - - - - - - - - - - - - - - - - -

                        #now RESET
                        self.cmd.write(bytearray(RESETInputCopy[3]))

                        steps = 1
                        while steps < self.canvas.stepNumber.get() + 1:

                            #perform the expected time delays and call the built in "readLines" function
                            #to extract the necessary information using Quotayba's established logic below

                            # This time is critical for receiving the correct data.
                            # I assume it is the time the board needs to send the first output.
                            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                            time.sleep(self.initSleepTime)
                            lines = self.readLines(expectedDelayRESET, [])
                                    
                            if lines and (len(lines) == len(expectedDelayRESET)):
                                output = RESETInputCopy.copy()
                                output[2] = cycle
                                output[3] = lines
                                self.outputQueue.put(output.copy())
                                self.progress += 1
                            else:
                                print("No output received: ", RESETInputCopy)
                                self.stopEvent.set()
                            steps += 1

                    cycle += 1 #increment to next cycle

            # - - - - - - - - - - - - - - - - - - - - - - - - - -

            else: #otherwise, FORM, SET or RESET states, all of which will be handled the same way (with all differences made before calling this function)

                recursionCopy = input.copy()

                # Send the input command
                self.cmd.resetBuffer()

                #perform the WHILE loops for the cycle logic here to avoid checking the IvTestState IF statements every cycle
                #for performance purposes
                cycle = 1
                while cycle < self.cycles+1:

                    self.cmd.write(bytearray(recursionCopy[3])) # input[3] is the byteList
                    
                    steps = 1
                    while steps < self.canvas.stepNumber.get() + 1:
                        
                        # This time is critical for receiving the correct data.
                        # I assume it is the time the board needs to send the first output.
                        # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
                        time.sleep(self.initSleepTime)
                        lines = self.readLines(self.expectedDelay, [])
                                
                        if lines and (len(lines) == len(self.expectedDelay)):
                            output = recursionCopy.copy()
                            output[2] = cycle
                            output[3] = lines
                            self.outputQueue.put(output.copy())
                            self.progress += 1
                        else:
                            print("No output received: ", recursionCopy)
                            self.stopEvent.set()
                        steps += 1
                    
                    cycle +=1

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {lines}")
            self.stopEvent.set()
            self.errorEvent.set()
        
    #- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def processRetentionInputPulseTest(self, input:list):
        lines = None
        try:
            # Send the input command
            self.cmd.resetBuffer()
            self.cmd.write(bytearray(input[3])) # input[3] is the byteList

            # This time is critical for receiving the correct data.
            # I assume it is the time the board needs to send the first output.
            # Make sure to adjust this if any change is made to the board or if you receive an empty lines.
            time.sleep(self.initSleepTime)
            lines = self.readLines(self.expectedDelay,[])
                    
            if lines and (len(lines) == len(self.expectedDelay)):
                output = input.copy()
                output[3] = lines
                self.outputQueue.put(output.copy())
                self.progress += 1
            else:
                print("No output received: ", input)
                self.stopEvent.set()

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {lines}")
            self.stopEvent.set()
            self.errorEvent.set()

    def processAllDevicesInputPulseTest(self, input:list):
        lines = None
        try:
            # Send the input command
            self.cmd.resetBuffer()
            self.cmd.write(bytearray(input[3])) # input[3] is the byteList

            if input[4]:
                self.expectedDelay = self.setResetRead2Delay
                input[4] = 'HRS'
            else:
                self.expectedDelay = self.setRead2Delay
                input[4] = 'LRS'

            time.sleep(self.initSleepTime)
            lines = self.readLines(self.expectedDelay,[])
                    
            if lines and (len(lines) == len(self.expectedDelay)):
                output = input.copy() 
                output[3] = lines
                self.outputQueue.put(output.copy())
                self.progress += 1
            else:
                print("No output received: ", input)
                self.stopEvent.set()

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {lines}")
            self.stopEvent.set()
            self.errorEvent.set()


    def processInputPulseRangeTest(self, input:list):
        print("Processing Pulse Range input ...") if self.debug else None
    
        # Read from the command until '\n' is received 
        try:
            # in the comments, 'cycles' refers to the maxCycles + 1, since both ends of voltage ranges are inclusive
			# if hard coding and this device needs to be in HRS, or not hard coding and HRS inputted
            if (self.canvas.applyToAllDevices.get() and input[4]) or \
                (not self.canvas.applyToAllDevices.get() and \
                self.canvas.hrsRangeMax.get() > 0): # input[4] is deviceStat
                expectedDelay = self.setResetRead2Delay
                maxCurr = self.hrsMaxCurr
                minCurr = self.hrsMinCurr
                stat = 'HRS'
                resetFirst = False
                # to put device into correct HRS range, a range of RESET voltages are used,
                # ranging from reset voltage in main block
                # to min reset voltage in Range Verification block
                # this will change every 'cycles' number of times the input is sent,
                # for 'cycles' number of times
                maxVoltage = int(self.canvas.resetVoltage.get() * 1000)
                minVoltage = int(self.canvas.minResetVoltage.get() * 1000)
                hrsOuterCycle = 1 # will run for 'cycles' x 'cycles' number of times
            # if hard coding and this device needs to be in LRS, or not hard coding and LRS inputted
            else:
                expectedDelay = self.setRead2Delay

                self.resetByteList[22] = input[1] # col
                self.resetByteList[23] = input[0] # row

                maxCurr = self.lrsMaxCurr
                minCurr = self.lrsMinCurr
                stat = 'LRS'
                resetFirst = True
                # to put device into correct LRS range, a range of GATE voltages are used,
                # ranging from end1 (gate voltage in main block)
                # to min gate voltage in Range Verification block)
                # this will change with each time the input is sent, for 'cycles' number of times
                maxVoltage = int(self.canvas.gateVoltage.get() * 1000)
                minVoltage = int(self.canvas.minGateVoltage.get() * 1000)
                hrsOuterCycle = self.maxCycles + 1 # will only for 'cycles' number of times

            # find the amount of voltage to step each time based on cycle number
            rangeStepVoltage = (maxVoltage - minVoltage) / self.maxCycles
            # set the starting GATE or RESET voltage to the min - step voltage,
            # since it will increase by the step voltage inside the while loops
            currentRangeVoltage = minVoltage - rangeStepVoltage

            # First read.
            self.read2ByteList[22] = input[1] # col
            self.read2ByteList[23] = input[0] # row

            self.cmd.resetBuffer()
            print(self.read2ByteList)
            self.cmd.write(bytearray(self.read2ByteList))
            time.sleep(self.initSleepTime)
            lines = self.readLines(self.read2Delay,[])
            reads = self.getValues(lines)

            if (reads['Read2']['Value'] <= maxCurr and reads['Read2']['Value'] >= minCurr):
                output = input.copy()
                output[2] = -1
                output[3] = reads
                output[4] = stat
                self.outputQueue.put(output)
                self.progress += 1
                return

            while hrsOuterCycle <= self.maxCycles + 1:
                # for HRS, we need to change the RESET voltage slightly in each hrsOuterCycle
                if not resetFirst:
                    currentRangeVoltage += rangeStepVoltage
                    input[3][14], input[3][15] = self.canvas.twoByteComboSplit(int(currentRangeVoltage))

                cycle = 1
                while cycle <= self.maxCycles+1:
                    # if LRS, a RESET command and then a SET command is needed; this does the RESET
                    if resetFirst:
                        self.cmd.resetBuffer()
                        print(self.resetByteList)
                        self.cmd.write(bytearray(self.resetByteList))
                        
                        time.sleep(self.initSleepTime)
                        _ = self.readLines(self.resetDelay,[])

                        # for LRS, we also need to change the GATE voltage slightly in each cycle
                        currentRangeVoltage += rangeStepVoltage
                        input[3][2], input[3][3] = self.canvas.twoByteComboSplit(int(currentRangeVoltage))

                    # Send the input command
                    self.cmd.resetBuffer()
                    print(input[3])
                    self.cmd.write(bytearray(input[3])) # input[3] is the byteList
                    time.sleep(self.initSleepTime)

                    lines = self.readLines(expectedDelay,[])
                            
                    if lines:
                        reads = self.getValues(lines) # get the value on 'uA' to avoid the unit changing in this loop.

                        # if current is within range or it's an LRS device and it's above the max,
                        # consider the device finished
                        if (reads['Read2']['Value'] <= maxCurr and reads['Read2']['Value'] >= minCurr) \
                            or (resetFirst and reads['Read2']['Value'] > maxCurr):
                            output = input.copy()
                            output [2] = cycle
                            output [3] = reads
                            output [4] = stat
                            self.csvInfo.append(currentRangeVoltage)
                            self.outputQueue.put(output)
                            self.progress += 1
                            return
                        else:
                            # if saving to CSV or this is the last cycle on this device, save the data
                            if self.saveIntermediateData or \
                                (cycle > self.maxCycles and hrsOuterCycle == self.maxCycles+1):
                                output = input.copy()
                                output[2] = cycle
                                output[3] = reads
                                output [4] = stat
                                self.csvInfo.append(currentRangeVoltage)
                                self.outputQueue.put(output)
                            cycle += 1

                    else:
                        print("No output received: ", print(f"[ {' | '.join([f'{x:02X}' for x in input[3]])} ]"))
                        self.stopEvent.set()
                        self.errorEvent.set()

                hrsOuterCycle += 1
            self.progress += 1 # done trying on this device

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {reads}")
            self.stopEvent.set()
            self.errorEvent.set()


    def processWriteImageInput(self, input:list):
        # Read from the command until '\n' is received
        try:
            # First read.
            self.read2ByteList[22] = input[1] # col
            self.read2ByteList[23] = input[0] # row

            self.cmd.resetBuffer()
            print(self.read2ByteList)
            self.cmd.write(bytearray(self.read2ByteList))

            val = input[4] * self.levelTolerance
            maxCurr = input[4] + val
            minCurr = input[4] - val

            time.sleep(self.initSleepTime)
            lines = self.readLines(self.read2Delay,[])
            reads = self.getValues(lines)
            if reads['Read2']['Value'] <= maxCurr and reads['Read2']['Value'] >= minCurr:
                output = input.copy()
                output[2] = -1
                output[3] = reads
                self.outputQueue.put(output)
                self.progress += 1
                return

            # into HRS modes
            if input[4] < self.rangeThreshold: # deviceStat
                expectedDelay = self.setResetRead2Delay
                currResetVoltage = self.baseResetVoltage
                resetStepVoltage = (self.maxResetVoltage - self.baseResetVoltage) / self.maxCycles
                outerCycle = 1
                while outerCycle < self.maxCycles+1:
                    input[3][14], input[3][15] = self.canvas.twoByteComboSplit(currResetVoltage)
                    cycle = 1
                    while cycle < self.maxCycles+1:
                        # Send the input command
                        self.cmd.resetBuffer()
                        print(input[3])
                        self.cmd.write(bytearray(input[3])) # input[3] is the byteList
                        
                        time.sleep(self.initSleepTime)
                        lines = self.readLines(expectedDelay,[])
                                
                        if lines:
                            reads = self.getValues(lines) # get the value on 'uA' to avoid the unit changing in this loop.

                            if reads['Read2']['Value'] <= maxCurr and reads['Read2']['Value'] >= minCurr:
                                output = input.copy()
                                output[2] = cycle
                                output[3] = reads
                                self.outputQueue.put(output)
                                self.progress += 1
                                return
                            else:
                                if self.saveIntermediateData or \
                                    (cycle > self.maxCycles and outerCycle == self.maxCycles):
                                    output = input.copy()
                                    output[2] = cycle
                                    output[3] = reads
                                    self.outputQueue.put(output)
                                cycle += 1         

                        else:
                            print("No output received: ", print(f"[ {' | '.join([f'{x:02X}' for x in input[3]])} ]"))
                            self.stopEvent.set()
                            self.errorEvent.set()
                            
                    currResetVoltage += resetStepVoltage
                    outerCycle += 1

                self.progress += 1

            # into LRS modes
            else:
                expectedDelay = self.setRead2Delay
                currGateVoltage = self.baseGateVoltage
                cycle = 1
                while currGateVoltage >= self.minGateVoltage:  
                    
                    self.resetByteList[22] = input[1]
                    self.resetByteList[23] = input[0]
                    self.cmd.resetBuffer()
                    print(self.resetByteList)
                    self.cmd.write(bytearray(self.resetByteList))
                    
                    time.sleep(self.initSleepTime)
                    _ = self.readLines(self.resetDelay,[])

                    input[3][2], input[3][3] = BaseCanvas.twoByteComboSplit(currGateVoltage)
                    # Send the input command
                    self.cmd.resetBuffer()
                    print(input[3])
                    self.cmd.write(bytearray(input[3])) # input[3] is the byteList
                    
                    time.sleep(self.initSleepTime)
                    lines = self.readLines(expectedDelay,[])
                            
                    if lines:
                        reads = self.getValues(lines) # get the value on 'uA' to avoid the unit changing in this loop.

                        if reads['Read2']['Value'] <= maxCurr and reads['Read2']['Value'] >= minCurr:
                            output = input.copy()
                            output[2] = cycle
                            output[3] = reads
                            output[5] = currGateVoltage
                            self.outputQueue.put(output)
                            self.progress += 1
                            return
                        else:
                            if self.saveIntermediateData or \
                                (currGateVoltage - self.gateVoltageStep < self.minGateVoltage):
                                output = input.copy()
                                output[2] = cycle
                                output[3] = reads
                                output[5] = currGateVoltage
                                self.outputQueue.put(output)
                            currGateVoltage -= self.gateVoltageStep
                            cycle += 1         

                    else:
                        print("No output received: ", print(f"[ {' | '.join([f'{x:02X}' for x in input[3]])} ]"))
                        self.stopEvent.set()
                        self.errorEvent.set()

                self.progress += 1

        except Exception as e:
            print(f"Error: {e}")
            print(f"Reads: {reads}")
            self.stopEvent.set()
            self.errorEvent.set()

    
    def processKernelProcessingInput(self, input:list):
        try:
            neighbors = self.getNeighbors(input[0], input[1])

            resultPix = 0

            for readVoltage, (row, col) in zip(self.kernel, neighbors):
                if (row < 0 or row >= self.gridSize) or (col < 0 or col >= self.gridSize) or readVoltage == 0:
                    continue
                sign = math.copysign(1, readVoltage)

                input[3][18], input[3][19] = BaseCanvas.twoByteComboSplit(abs(readVoltage))
                input[3][22] = col
                input[3][23] = row

                self.cmd.resetBuffer()
                self.cmd.write(bytearray(input[3])) # input[3] is the byteList

                time.sleep(self.initSleepTime)
                lines = self.readLines(self.read2Delay,[])
                        
                if lines and (len(lines) == len(self.read2Delay)):
                    reads = self.getValues(lines)
                    resultPix += sign * reads['Read2']['Value'] 
                else:
                    print("No output received: ", input)
                    self.stopEvent.set()

            output = input.copy()
            
            output[3] = resultPix
            self.outputQueue.put(output)
            self.progress += 1

        except Exception as e:
            print(f"Error: {e}")
            self.stopEvent.set()
            self.errorEvent.set()

# --------------------------------------------------------------------------------------------------
                                # OUTPUT TARGET FUNCTIONS
# ----------------------------------------------------------------------------------------------------
    
    def processOutputPulseTest(self, output):
        """
        Process the output from the input queue. Extract data from the output
        lines and update the results DataFrame.

        Args:
            output (list): A list containing the row, column, cycle, and output
                lines from the command.
        """
        print("Processing output ...") if self.debug else None
        
        # Extract the channel data and current readings from the output lines
        reads = self.getValues(output[3]) # output[3] is the lines.

        # see the init function.
        # self.initNewRow is either init_newRow or init_AllDevices_newRow depend on allDevices option.
        new_row = self.initNewRow(output)

        for readName, item in reads.items():

            # The reads is a dictionary with keys 'Channel' and 'Value'
            # Add the channel data to the new row
            new_row[f"{readName} Ch"] = item['Channel']
            
            # Add the current reading  to the new row
            new_row[readName] = item['Value']
            if new_row[readName] == 0.-1:
                new_row[readName] = 0

        print("New row:", new_row) #if self.debug else None # commented out so it always prints
        # Concatenate the new row to the results DataFrame
        with self.results_lock:
            self.results = pd.concat([self.results, pd.DataFrame([new_row])], ignore_index=True)

        if self.canvas.csvControlVariable.get():
            # if this is a new CSV file, open with 'w'
            if self.csvRows % 1000000 == 0:
                self.csvSheet += 1
                openVar = 'w'
            # otherwise, open with 'a'
            else:
                openVar = 'a'
            fileName = f"data_{self.csvSheet}.csv"
            filePath = os.path.join(self.csvMgr.folderDirectory, fileName)
            with open(filePath, openVar) as file:
                # if this is a new CSV file, write the headers
                if openVar == 'w':
                    infoLines = self.csvMgr.getInfoLines(self.canvas)
                    for line in infoLines:
                        file.write('# ' +line + "\n")
                    file.write('\n')
                    header = list(new_row)
                    if self.canvas.modeState.get() == 'pulse_step_test':
                        if self.canvas.stepVoltageDirection.get() == 'Rise then Fall':
                            header.insert(3, 'Set or Reset')
                        header.insert(4, 'Steps')
                        if self.canvas.incrementVoltage.get():
                            header.insert(5, 'Voltage')
                    elif (self.canvas.modeState.get() == 'pulse_cycle_test') and \
                        ('Read1' in header):
                        header.append('Read2 Ch')
                        header.append('Read2')
                    # use correct unit
                    if self.canvas.toggledOhmsLawUnit.get() == 'uA':
                        header = ['Read1 (uA)' if x == 'Read1' else x for x in header]
                        header = ['Read2 (uA)' if x == 'Read2' else x for x in header]
                    else:
                        header = ['Read1 (kOhm)' if x == 'Read1' else x for x in header]
                        header = ['Read2 (kOhm)' if x == 'Read2' else x for x in header]
                    file.write(','.join(str(h) for h in header) + '\n')
                
                self.csvRows += 1
                # write the new row in manually
                values = []
                for idx in new_row:
                    if pd.isna(new_row[idx]):
                        values.append('')
                    elif idx == 'cycle':
                        values.append(str(new_row[idx]))
                        # if this is a step test, add the csvInfo needed
                        if self.canvas.modeState.get() == 'pulse_step_test':
                            if self.canvas.stepVoltageDirection.get() == 'Rise then Fall':
                                values.append(str(self.csvInfo.pop(0)))
                            values.append(str(self.csvInfo.pop(0)))
                            if self.canvas.incrementVoltage.get():
                                values.append(str(self.csvInfo.pop(0)))
                    # the unit conversions are copied from convert_column in getData
                    elif self.canvas.toggledOhmsLawUnit.get() != 'uA' \
                        and idx == 'Read1':
                        current = new_row[idx]
                        zero_mask = current == 0
                        # Avoid division by zero, use maximum float value instead
                        resistance = np.round(np.where(
                            zero_mask,
                            np.finfo(np.float16).max,
                            (self.readVoltages[0] / current))
                        , 2) # round to 2 decimal places
                        values.append(str(resistance))
                    elif idx == 'Read2 Ch':
                        # if this cycle/step has no read1 but others do, must skip columns
                        if ('Read1 Ch' not in new_row) and self.results.shape[1] > 6:
                            values.append('')
                            values.append('')
                        values.append(str(new_row[idx]))
                    elif self.canvas.toggledOhmsLawUnit.get() != 'uA' \
                        and idx == 'Read2':
                            current = new_row[idx]
                            zero_mask = current == 0
                            # Avoid division by zero, use maximum float value instead
                            resistance = np.round(np.where(
                                zero_mask,
                                np.finfo(np.float16).max,
                                (self.readVoltages[1] / current))
                            , 2) # round to 2 decimal places
                            values.append(str(resistance))
                    else:
                        values.append(str(new_row[idx]))
                file.write(','.join(values) + '\n')

    def processOutputPulseRangeTest(self, output):
        new_row = self.initNewRow(output)
        for readName, item in output[3].items():
            # The reads is a dictionary with keys 'Channel' and 'Value'
            # Add the channel data to the new row
            new_row[f"{readName} Ch"] = item['Channel']
            
            # Add the current reading  to the new row
            new_row[readName] = item['Value']

        print("New row:", new_row) #if self.debug else None # commented out so it always prints

        if self.canvas.csvControlVariable.get():
            # if this is a new CSV file, open with 'w'
            if self.csvRows % 1000000 == 0:
                self.csvSheet += 1
                openVar = 'w'
            # otherwise, open with 'a'
            else:
                openVar = 'a'
            fileName = f"data_{self.csvSheet}.csv"
            filePath = os.path.join(self.csvMgr.folderDirectory, fileName)
            with open(filePath, openVar) as file:
                # if this is a new CSV file, write the headers
                if openVar == 'w':
                    infoLines = self.csvMgr.getInfoLines(self.canvas)
                    for line in infoLines:
                        file.write('# ' +line + "\n")
                    file.write('\n')
                    header = list(new_row)
                    # add the required columns for gate and/or reset voltage to header
                    if self.canvas.applyToAllDevices.get():
                        header.insert(4, 'Gate Voltage (mV)')
                        header.insert (5, 'Reset Voltage (mV)')
                    elif self.canvas.lrsRangeMax.get() > 0:
                        header.insert(4, 'Gate Voltage (mV)')
                    else:
                        header.insert(4, 'Reset Voltage (mV)')
                    # use correct unit
                    if self.canvas.toggledOhmsLawUnit.get() == 'uA':
                        header = ['Read1 (uA)' if x == 'Read1' else x for x in header]
                        header = ['Read2 (uA)' if x == 'Read2' else x for x in header]
                    else:
                        header = ['Read1 (kOhm)' if x == 'Read1' else x for x in header]
                        header = ['Read2 (kOhm)' if x == 'Read2' else x for x in header]
                    file.write(','.join(str(h) for h in header) + '\n')
                
                self.csvRows += 1
                # write the new row in manually
                values = []
                for idx in new_row:
                    if pd.isna(new_row[idx]):
                        values.append('')
                    elif idx == 'status':
                        # add in the cycle and then the gate and/or reset voltages
                        values.append(str(new_row[idx]))
                        if new_row['cycle'] == -1:
                            values.append('')
                            if self.canvas.applyToAllDevices.get():
                                values.append('')
                            continue
                        if new_row[idx] == 'LRS':
                            values.append(str(self.csvInfo.pop(0)))
                        if self.canvas.applyToAllDevices.get():
                            values.append('')
                        if new_row[idx] == 'HRS':
                            values.append(str(self.csvInfo.pop(0)))
                    # the unit conversions are copied from convert_column in getData
                    elif self.canvas.toggledOhmsLawUnit.get() != 'uA' \
                        and idx == 'Read1':
                        current = new_row[idx]
                        zero_mask = current == 0
                        # Avoid division by zero, use maximum float value instead
                        resistance = np.round(np.where(
                            zero_mask,
                            np.finfo(np.float16).max,
                            (self.readVoltages[0] / current))
                        , 2) # round to 2 decimal places
                        values.append(str(resistance))
                    elif self.canvas.toggledOhmsLawUnit.get() != 'uA' \
                        and idx == 'Read2':
                        current = new_row[idx]
                        zero_mask = current == 0
                        # Avoid division by zero, use maximum float value instead
                        resistance = np.round(np.where(
                            zero_mask,
                            np.finfo(np.float16).max,
                            (self.readVoltages[1] / current))
                        , 2) # round to 2 decimal places
                        values.append(str(resistance))
                    else:
                        values.append(str(new_row[idx]))
                file.write(','.join(values) + '\n')
        
        # Concatenate the new row to the results DataFrame
        with self.results_lock:
            self.results = pd.concat([self.results, pd.DataFrame([new_row])], ignore_index=True)

    def processKernelTestOutput(self, output):
        new_row = self.initNewRow(output)
        new_row['Read2'] = abs(output[3]) 

        print("New row:", new_row) #if self.debug else None # commented out so it always prints

        if self.canvas.csvControlVariable.get():
            # if this is a new CSV file, open with 'w'
            if self.csvRows % 1000000 == 0:
                self.csvSheet += 1
                openVar = 'w'
            # otherwise, open with 'a'
            else:
                openVar = 'a'
            fileName = f"data_{self.csvSheet}.csv"
            filePath = os.path.join(self.csvMgr.folderDirectory, fileName)
            with open(filePath, openVar) as file:
                # if this is a new CSV file, write the headers
                if openVar == 'w':
                    infoLines = self.csvMgr.getInfoLines(self.canvas)
                    for line in infoLines:
                        file.write('# ' +line + "\n")
                    file.write('\n')
                    header = list(new_row)
                    # use correct unit
                    if self.canvas.toggledOhmsLawUnit.get() == 'uA':
                        header = ['Read1 (uA)' if x == 'Read1' else x for x in header]
                        header = ['Read2 (uA)' if x == 'Read2' else x for x in header]
                    else:
                        header = ['Read1 (kOhm)' if x == 'Read1' else x for x in header]
                        header = ['Read2 (kOhm)' if x == 'Read2' else x for x in header]
                    file.write(','.join(str(h) for h in header) + '\n')
                
                self.csvRows += 1
                # write the new row in manually
                values = []
                for idx in new_row:
                    if pd.isna(new_row[idx]):
                        values.append('')
                    # the unit conversions are copied from convert_column in getData
                    elif self.canvas.toggledOhmsLawUnit.get() != 'uA' \
                        and idx == 'Read1':
                        current = new_row[idx]
                        zero_mask = current == 0
                        # Avoid division by zero, use maximum float value instead
                        resistance = np.round(np.where(
                            zero_mask,
                            np.finfo(np.float16).max,
                            (self.readVoltages[0] / current))
                        , 2) # round to 2 decimal places
                        values.append(str(resistance))
                    elif self.canvas.toggledOhmsLawUnit.get() != 'uA' \
                        and idx == 'Read2':
                        current = new_row[idx]
                        zero_mask = current == 0
                        # Avoid division by zero, use maximum float value instead
                        resistance = np.round(np.where(
                            zero_mask,
                            np.finfo(np.float16).max,
                            (self.readVoltages[1] / current))
                        , 2) # round to 2 decimal places
                        values.append(str(resistance))
                    else:
                        values.append(str(new_row[idx]))
                file.write(','.join(values) + '\n')

        # Concatenate the new row to the results DataFrame
        with self.results_lock:
            self.results = pd.concat([self.results, pd.DataFrame([new_row])], ignore_index=True)

    #- - - - - - - - - - - - - - - - - - - - - - - - - -

    #function to process the to be outputted data from the input thread
    #for the IV test given its unique format, extracting the data from the
    #inputted "output" lines to update the results Pandas DataFrame used
    #for the execution thread
    
    #NOTE: output list format: row, column, cycle, and output lines

    #NOTE: 1.1 IV Test output format (with each line be printed PER STEP)
    ##(when rising) RISING-Read1 V = # mV ; I = # uA
    #(when falling) FALLING-Read1 V = # mV ; I = # uA

    #NOTE: The 1.1 IV Test output does NOT have channel number information, unlike
    #all other Pulse Test formats

    #NOTE: Upon testing with various time delays, it was found that the data read into the program
    #manages to get two steps EVERY TIME, so the code below is designed to cycle through all outputted
    #lines within output if there's more than one
    def processOutputIVTest(self, output):

        #print display to show that the code is within this function when debugging

        print("Processing IV Test output ...") if self.debug else None
        
        #obtain the voltage and current outputs from the unique IV Test output lines
        #by calling the "getValuesIV" function
        reads = self.getValuesIV(output[3]) # output[3] is the lines.

        # - - - - - - - - - - - - - - - - - - -

        #get the length of the key values to see if a list with a length > 1 has
        #been made
        for readName, item in reads.items():
            self.valueListLength = len(item['Voltage'])
            break
        
        # - - - - - - - - - - - - - - - - - - -

        #create a new row for EACH key value depending on the found value list length (all shared,
        #so "Voltage" was chosen for the sake of selecting one)
        for valueListIndex in range(self.valueListLength):
            
            #call the assigned initNewRow function as defined within the init
            #function based on modeState (which is for the "iv_test" this time)
            #prepare the row/column/cycle basic formatting before adding further details
            new_row = self.initNewRow(output)

            for readName, item in reads.items():
                
                #reads is a dictionary with keys 'Voltage', 'Current' and 'State' for IV tests
                new_row[f"{readName} Output Voltage"] = item['Voltage'][valueListIndex] #add voltage information to new line in results to output
                new_row[f"{readName} Output Current"] = item['Current'][valueListIndex] #add current information to new line in results to output
                new_row[f"{readName} Direction State"] = item['State'][valueListIndex] #add state information to new line in results to output

            print("New row:", new_row) #if self.debug else None # commented out so it always prints

            if self.canvas.csvControlVariable.get():
                # if this device is already in results, it has at least one CSV already
                if (not self.results.empty and \
                    self.results.iloc[-1, 0] == new_row['row'] and \
                    self.results.iloc[-1, 1] == new_row['col']):
                    # if this is a new CSV file, open with 'w'
                    if self.csvRows % 1000000 == 0:
                        self.csvSheet += 1
                        openVar = 'w'
                    # otherwise, open with 'a'
                    else:
                        openVar = 'a'
                # if this device is not in results, it does not have a CSV yet
                else:
                    # reset rows, sheets, and open with 'w'
                    self.csvRows = 0
                    self.csvSheet = 1
                    openVar = 'w'
                
                fileName = f"data_deviceR{new_row['row']}_C{new_row['col']}_{self.csvSheet}.csv"
                filePath = os.path.join(self.csvMgr.folderDirectory, fileName)
                with open(filePath, openVar) as file:
                    # if this is a new CSV file, write the headers
                    if openVar == 'w':
                        infoLines = self.csvMgr.getInfoLines(self.canvas)
                        for line in infoLines:
                            file.write('# ' +line + "\n")
                        file.write('\n')
                        header = list(new_row)
                        if 'Read1 Output Voltage' in header and \
                            self.canvas.IvTestState.get() == 'IV':
                            header.append('Read2 Output Voltage')
                            header.append('Read2 Output Current')
                            header.append('Read2 Direction State')
                        file.write(','.join(str(h) for h in header) + '\n')
                    
                    self.csvRows += 1
                    # write the new row in manually
                    values = []
                    for idx in new_row:
                        if pd.isna(new_row[idx]):
                            values.append('')
                        # if this is the start of the 3 read2 values, skip the read1 slots if needed
                        elif idx == 'Read2 Output Voltage' and \
                            self.canvas.IvTestState.get() == 'IV':
                            values.append('')
                            values.append('')
                            values.append('')
                            values.append(str(new_row[idx]))
                        else:
                            values.append(str(new_row[idx]))
                    file.write(','.join(values) + '\n')

            # Concatenate the new row to the results DataFrame
            with self.results_lock:
                self.results = pd.concat([self.results, pd.DataFrame([new_row])], ignore_index=True)

# --------------------------------------------------------------------------------------------------
                                # EXECUTE TARGETs
# ----------------------------------------------------------------------------------------------------

    def createPulseTestPlots(self):

        '''
        print('create Save plots bool in createPulseTestPlots')
        print(self.canvas.createSavePlots.get())
        print('----------------------')
        print('----------------------')
        '''
            
        if self.canvas.createSavePlots.get():

            print("\nMaking New Scatter Plot ...\n") if self.debug else None

            '''
            print('debugging')
            self.newPlotDataEventHeatMap.set()
            '''

            data = self.getData(self.canvas.toggledOhmsLawUnit.get())

            try:
                # Group by unique devices (row, col)
                for (row, col), group in data.groupby(['row', 'col']):
                    device = f"({row}-{col})"
                    read1 = None
                    read2 = None

                    try:
                        # Extract Read1 and Read2 time series per device over cycles
                        if 'Read1' in group.columns:
                            read1_values = group[['cycle', 'Read1']].set_index('cycle').sort_index()
                            read1 = (f"{device}", read1_values)
                        else: # allows plots to be created even without read1
                            read1 = (f"{device}", pd.DataFrame())

                        if 'Read2' in group.columns:
                            read2_values = group[['cycle', 'Read2']].set_index('cycle').sort_index()
                            read2 = (f"{device}", read2_values)
                        
                        if self.canvas.applyToAllDevices.get():
                            # if the device is in LRS, the data must go in read1
                            # because otherwise, it will be displayed as an HRS device in the plots
                            if group['status'].isin(['LRS']).any():
                                read1 = read2
                                read2 = None
                            # if it's HRS, read1 only contains the device data and not the reads,
                            #  so that UpdatePlots can run but only adds read2 data
                            else:
                                read1 = (f"{device}", pd.DataFrame())
                        
                        # in IV testing, the outputs are split between voltage and current
                        if 'Read1 Output Current' in group.columns:
                            read1_values = group[['cycle', 'Read1 Output Current']] \
                                .dropna(subset=['Read1 Output Current']).set_index('cycle').sort_index()
                            read1_volts = group[['cycle', 'Read1 Output Voltage']] \
                                .dropna(subset=['Read1 Output Voltage']).set_index('cycle').sort_index()
                            read1 = (f"{device}", read1_values, read1_volts)
                        if 'Read2 Output Current' in group.columns:
                            # allows RESET IV testing to be done by putting device in read1 but no reads
                            if 'Read1 Output Current' not in group.columns:
                                read1 = (f"{device}", pd.DataFrame(), pd.DataFrame())

                            read2_values = group[['cycle', 'Read2 Output Current']] \
                                .dropna(subset=['Read2 Output Current']).set_index('cycle').sort_index()
                            read2_volts = group[['cycle', 'Read2 Output Voltage']] \
                                .dropna(subset=['Read2 Output Voltage']).set_index('cycle').sort_index()
                            if self.canvas.IvTestState.get() == 'IV':
                                read2_values = -read2_values
                                read2_volts = -read2_volts
                            read2 = (f"{device}", read2_values, read2_volts)

                        with self.plotDataLock:
                            self.plotDataDict[device] = {'Read1': read1, 'Read2': read2}
                            self.newPlotDataEvent.set()
                            '''
                            print('testing within createPulseTestPlots')
                            print(self.newPlotDataEvent.is_set())
                            print('-----------------')
                            '''

                    except Exception as e:
                        print(f"Error processing device {device}: {e}")
                        print(f"group: {group}")
                        self.stopEvent.set()
                        self.errorEvent.set()

            except Exception as e:
                print(f"General Error: {e}")
                self.stopEvent.set()
                self.errorEvent.set()
            
            print("updating plots ...") if self.debug else None

        #- - - - - - - - - - - - - - - - - - - - - - - - - - -
            
        if self.canvas.createHeatMap.get():
            print("\nMaking New Heat Map ...\n") if self.debug else None
            data = self.getData(self.canvas.toggledOhmsLawUnit.get())

            # if this is just a plain pulse test that is in form mode, only the final reads on each
            # device should be in one heatmap together
            if self.canvas.formSetStateString.get() == 'FORM' and self.canvas.modeState.get() == \
                'pulse_test' and not self.canvas.utilizeCurResRange.get() and not \
                self.canvas.kernelProcessingTest.get() and not (self.canvas.writeImage.get() and \
                not self.canvas.binaryMode.get()) and not self.canvas.applyToAllDevices.get() and \
                not self.canvas.retentionTest.get():
                
                # Ensure 'cycle' is numeric
                data['cycle'] = pd.to_numeric(data['cycle'], errors='coerce')

                # Find index of the largest cycle per (row, col)
                idx = data.groupby(['row', 'col'])['cycle'].idxmax()

                # Select those rows
                group:pd.DataFrame = data.loc[idx].reset_index(drop=True)
                read1 = read2 = None
                fullIndex = range(64)
                try:
                    # Pivot read1 and read2 into grids
                    if 'Read1' in data.columns:
                        # Create a pivot table of the data, with the row and column indices
                        # sorted by their integer values
                        grid_read1 = group.pivot(index='row', columns='col', values='Read1')
                        grid_read1 = grid_read1.sort_index().sort_index(axis=1)
                        grid_read1 = grid_read1.reindex(index=fullIndex, columns=fullIndex)

                        # Optional: Replace missing entries explicitly with NaN
                        grid_read1 = grid_read1.astype('float')  # ensure it's float dtype with NaNs allowed
                        read1 = (f"Read1 - Final Cycle - {self.canvas.toggledOhmsLawUnit.get()}", grid_read1)
                        
                    if 'Read2' in data.columns:
                        # Create a pivot table of the data, with the row and column indices
                        # sorted by their integer values
                        grid_read2 = group.pivot(index='row', columns='col', values='Read2')
                        grid_read2 = grid_read2.sort_index().sort_index(axis=1) 
                        grid_read2 = grid_read2.reindex(index=fullIndex, columns=fullIndex)
                        
                        # Optional: Replace missing entries explicitly with NaN
                        grid_read2 = grid_read2.astype('float')  # ensure it's float dtype with NaNs allowed

                        read2 = (f"Read2 - Final Cycle - {self.canvas.toggledOhmsLawUnit.get()}", grid_read2)

                    with self.plotDataHeatMapLock:
                        self.plotDataDictHeatMap['Final'] = {'Read1':read1, 'Read2':read2}
                        self.newPlotDataEventHeatMap.set()
                except Exception as e:
                        print(f"Error: {e}")
                        print(f"group: {group}")
                        self.stopEvent.set()
                        self.errorEvent.set()

            else:
                fullIndex = range(64)
                for cycle, group in data.groupby('cycle'):
                    read1 = None
                    read2 = None
                    grid_read1 = pd.DataFrame()
                    grid_read2 = pd.DataFrame()
                    # Pivot read1 and read2 into grids
                    try:
                        if 'Read1' in data.columns:
                            # Create a pivot table of the data, with the row and column indices
                            # sorted by their integer values
                            grid_read1 = group.pivot(index='row', columns='col', values='Read1')
                            grid_read1 = grid_read1.sort_index().sort_index(axis=1)
                            grid_read1 = grid_read1.reindex(index=fullIndex, columns=fullIndex)
            
                            # Optional: Replace missing entries explicitly with NaN
                            grid_read1 = grid_read1.astype('float')  # ensure it's float dtype with NaNs allowed
                            read1 = (f"Read1 - Cycle {cycle}", grid_read1)
                            
                        if 'Read2' in data.columns:
                            # Create a pivot table of the data, with the row and column indices
                            # sorted by their integer values
                            grid_read2 = group.pivot(index='row', columns='col', values='Read2')
                            grid_read2 = grid_read2.sort_index().sort_index(axis=1) 
                            grid_read2 = grid_read2.reindex(index=fullIndex, columns=fullIndex)
                            
                            # Optional: Replace missing entries explicitly with NaN
                            grid_read2 = grid_read2.astype('float')  # ensure it's float dtype with NaNs allowed

                            read2 = (f"Read2 - Cycle {cycle}", grid_read2)

                        with self.plotDataHeatMapLock:
                            self.plotDataDictHeatMap[cycle] = {'Read1':read1, 'Read2':read2}
                            self.newPlotDataEventHeatMap.set()
                    except Exception as e:
                        print(f"Error: {e}")
                        print(f"group: {group}")
                        self.stopEvent.set()
                        self.errorEvent.set()
                
    

    def createCSV(self):
        
        print("Finish Target is called ...") if self.debug else None
        if self.canvas.csvControlVariable.get():
            # print("Creating CSV files ...") if self.debug else None

            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            #create the .csv file with the base data information without
            #special formatting here

            #NOTE: Depending on the chosen modeState, additional information that is to
            #be outputted will need to be added in here before calling the "export_to_csv"
            #function in the CSVManager (self.csvMgr) program file

            #first, get the expected universal information with the info_lines statistics
            #and the actually results for all outputted lines of data
            info_lines = self.csvMgr.getInfoLines(self.canvas)
            results = self.getData(self.canvas.toggledOhmsLawUnit.get())

            #add the additional information here based on the selected modeState
            #NOTE: Additional information is NOT required for the default Pulse Test
            # match self.canvas.modeState.get():
                
            #     case 'pulse_test':
            #         if self.canvas.utilizeCurResRange.get():
            #             # if doing range verification,
            #             # make voltage column(s) depending on HRS (reset voltage varies) or LRS (gate voltage varies)
            #             # if hard coding, both if statements will be triggered
            #             if (self.canvas.utilizeCurResRange.get()):
            #                 if (self.canvas.lrsRangeMax.get() > 0): # need the gate voltages
            #                     maxVoltage = int(self.canvas.gateVoltage.get() * 1000)
            #                     minVoltage = int(self.canvas.minGateVoltage.get() * 1000)
            #                     rangeStepVoltage = (maxVoltage - minVoltage) / self.maxCycles
            #                     # this series only has 1 repetition of the voltages
            #                     gateVoltageData = pd.Series(list(np.arange(minVoltage, maxVoltage + rangeStepVoltage, rangeStepVoltage).astype(int)))
            #                     gateVoltageData.name = 'Gate Voltage (mV)' #add a column name to the new series
                                    
            #                     results['Gate Voltage (mV)'] = np.nan
            #                     cycle_map = {i+1: v for i, v in enumerate(gateVoltageData)}
            #                     condition = results['status'] == 'LRS' # only add to LRS status, in case we are hard coding
            #                     results.loc[condition, 'Gate Voltage (mV)'] = results.loc[condition, 'cycle'].map(cycle_map)

            #                     gateVoltCol = results.pop('Gate Voltage (mV)')
            #                     results.insert(4, 'Gate Voltage (mV)', gateVoltCol)
                            
            #                 if (self.canvas.hrsRangeMax.get() > 0): # need the reset voltages
            #                     maxVoltage = int(self.canvas.resetVoltage.get() * 1000)
            #                     minVoltage = int(self.canvas.minResetVoltage.get() * 1000)
            #                     rangeStepVoltage = (maxVoltage - minVoltage) / self.canvas.pulseTestRangeCycleCount.get()
            #                     # this series only has 1 repetition of the voltages
            #                     resetVoltageData = pd.Series(list(np.arange(minVoltage, maxVoltage + rangeStepVoltage, rangeStepVoltage).astype(int)))
            #                     resetVoltageData.name = 'Reset Voltage (mV)' #add a column name to the new series
                                
            #                     results['Reset Voltage (mV)'] = np.nan
            #                     cycle_index = -1
            #                     row = results.at[0, 'row']
            #                     col = results.at[0, 'col']
            #                     for i, pos in enumerate(results['cycle']):
            #                         if pos == 1: # start of a new cycle
            #                             cycle_index += 1
            #                         if results.at[i, 'row'] != row or results.at[i, 'col'] != col: # start of a new device
            #                             row = results.at[i, 'row']
            #                             col = results.at[i, 'col']
            #                             cycle_index = 0
            #                         # only add to HRS status, in case we are hard coding
            #                         if pos != -1 and cycle_index < len(resetVoltageData) and results.at[i, 'status'] == 'HRS':
            #                             results.at[i, 'Reset Voltage (mV)'] = resetVoltageData.iloc[cycle_index]
                                
            #                     resetVoltCol = results.pop('Reset Voltage (mV)')
            #                     results.insert(4, 'Reset Voltage (mV)', resetVoltCol)

            #     case 'pulse_step_test':

            #         #for counting the total number of expected steps in the .csv file, the device number
            #         #is needed and will be calculated here instead of calling other files at this time
            #         #to avoid any parent dependencies
            #         #NOTE: Each selected device will be chosen by each UNIQUE COMBINATION of the rows and columns
            #         rowColCombinations = results.groupby(['row', 'col'])
            #         combinationCount = len(rowColCombinations)

            #         #add step column to results before submitting to export_to_csv
            #         #NOTE: Creating the step information by creating a list of steps from 1
            #         #to the submitted stepNumber and repeating this for each cycle by recreating
            #         #the step list multiple times (equal to the cycleNumber)
                    
            #         # adding a column for the steps and the voltages used in each step,
            #         # mostly copied from StepsData and processInputPulseStepTest
            #         if (self.canvas.incrementVoltage.get()): # if voltage is incrementing, both steps and voltage cols added
            #             if(self.canvas.chosenStepVoltage.get() == 'SET'): #if SET, use FORM/SET voltage
            #                 maxStepVoltage = int(self.canvas.maxFormSetVoltage.get() * 1000)
            #                 minStepVoltage = int(self.canvas.formSetVoltage.get() * 1000)
            #             else: #otherwise, RESET, use RESET voltage
            #                 maxStepVoltage = int(self.canvas.maxResetVoltage.get() * 1000)
            #                 minStepVoltage = int(self.canvas.resetVoltage.get() * 1000)
            #             stepVoltage = abs(maxStepVoltage - minStepVoltage) / self.canvas.stepNumber.get()

            #             if self.canvas.stepVoltageDirection.get() == 'Rising':  # if in rising direction, voltage increases
            #                 StepsData = pd.Series(list(range(0, self.canvas.stepNumber.get() + 1)) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the step integer list; used to have index=results.index
            #                 VoltageData = pd.Series(list(np.arange(minStepVoltage, maxStepVoltage + stepVoltage, stepVoltage).astype(int)) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the voltage integer list
                        
            #             elif self.canvas.stepVoltageDirection.get() == 'Falling':   # if in falling direction, voltage decreases
            #                 StepsData = pd.Series(list(range(0, self.canvas.stepNumber.get() + 1)) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the step integer list; used to have index=results.index
            #                 VoltageData = pd.Series(list(np.arange(maxStepVoltage, minStepVoltage - stepVoltage, -stepVoltage).astype(int)) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the voltage integer list

            #             else:   # if rise then fall, steps must repeat and both of the rising operation voltages must be included
            #                 oneRiseSteps = list(range(0, (self.canvas.stepNumber.get()) + 1)) # amount of steps for one rise operatoin
            #                 StepsData = pd.Series((oneRiseSteps + oneRiseSteps) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the step integer list; used to have index=results.index
            #                 firstRiseVoltages = list(np.arange(minStepVoltage, maxStepVoltage + stepVoltage, stepVoltage).astype(int))
                            
            #                 # change min and max voltages to the opposite of the ones in the first rise operation
            #                 # must also have a column denoting which voltages are set or reset
            #                 if(self.canvas.chosenStepVoltage.get() == 'RESET'): #if RESET, use FORM/SET voltage
            #                     maxStepVoltage = int(self.canvas.maxFormSetVoltage.get() * 1000)
            #                     minStepVoltage = int(self.canvas.formSetVoltage.get() * 1000)
            #                     firstSetResetCol = list(['R'] * len(oneRiseSteps))
            #                     secondSetResetCol = list(['S'] * len(oneRiseSteps))
            #                 else: #otherwise, SET, use RESET voltage
            #                     maxStepVoltage = int(self.canvas.maxResetVoltage.get() * 1000)
            #                     minStepVoltage = int(self.canvas.resetVoltage.get() * 1000)
            #                     firstSetResetCol = list(['S'] * len(oneRiseSteps))
            #                     secondSetResetCol = list(['R'] * len(oneRiseSteps))

            #                 stepVoltage = abs(maxStepVoltage - minStepVoltage) / self.canvas.stepNumber.get()
            #                 secondRiseVoltages = list(np.arange(minStepVoltage, maxStepVoltage + stepVoltage, stepVoltage).astype(int))
            #                 VoltageData = pd.Series((firstRiseVoltages + secondRiseVoltages) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the voltage integer list
            #                 setResetCol = pd.Series((firstSetResetCol + secondSetResetCol) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create a Pandas Series with 'S' for SET and 'R' for RESET
            #                 setResetCol.name = 'Set or Reset' #add a column name to the new setResetCol
            #                 results.loc[results['cycle'] != 0, 'Set or Reset'] = setResetCol.values # add SET/RESET column to results dataFrame
            #                 setResetCol = results.pop('Set or Reset') # move to proper position
            #                 results.insert(3, 'Set or Reset', setResetCol)

            #             StepsData.name = 'Steps' #add a column name to the new StepsData
            #             VoltageData.name = 'Voltage (mV)' #add a column name to the new VoltageData

            #             #toConcatWithSteps = [results.copy(), StepsData] #create the list before concatenating the data together
            #             #results = pd.concat([s.reset_index(drop=True) for s in toConcatWithSteps], axis=1) #concatenate horizontally (axis = 1) to add to furthest right column
            #             results.loc[results['cycle'] != 0, 'Steps'] = StepsData.values

            #             #toConcatWithVoltage = [results.copy(), VoltageData] #create the list before concatenating the data together
            #             #results = pd.concat([s.reset_index(drop=True) for s in toConcatWithVoltage], axis=1) #concatenate horizontally (axis = 1) to add to furthest right column
            #             results.loc[results['cycle'] != 0, 'Voltage (mV)'] = VoltageData.values
            #             # depending on which read will be used for the step measurements, put the steps and voltage before it
            #             stepCol = results.pop('Steps')
            #             voltCol = results.pop('Voltage (mV)')
            #             if (self.canvas.stepVoltageDirection.get() == 'Rise then Fall'): # RISE THEN FALL, both reads will be used
            #                 results.insert(4, 'Steps', stepCol)
            #                 results.insert(5, 'Voltage (mV)', voltCol)
            #             elif (self.canvas.chosenStepVoltage.get() == 'SET'):  # SET, read 1 will be used
            #                 results.insert(3, 'Steps', stepCol)
            #                 results.insert(4, 'Voltage (mV)', voltCol)
            #             else:   # RESET, read 2 will be used
            #                 results.insert(5, 'Steps', stepCol)
            #                 results.insert(6, 'Voltage (mV)', voltCol)

            #         else: # if voltage was not incremented, only steps col added
            #             if self.canvas.stepVoltageDirection.get() != 'Rise then Fall': # if not RISE THEN FALL, only STEPS amount of steps
            #                 StepsData = pd.Series(list(range(1, self.canvas.stepNumber.get() + 1)) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the step integer list; used to have index=results.index

            #             else:   # if rise then fall, steps must repeat and a SET or RESET column is needed
            #                 oneRiseSteps = list(range(1, (self.canvas.stepNumber.get()) + 1)) # amount of steps for one rise operatoin
            #                 StepsData = pd.Series((oneRiseSteps + oneRiseSteps) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create Pandas Series with the step integer list; used to have index=results.index
            #                 if(self.canvas.chosenStepVoltage.get() == 'RESET'): #if RESET, 'R' first in set/reset col
            #                     firstSetResetCol = list(['R'] * len(oneRiseSteps))
            #                     secondSetResetCol = list(['S'] * len(oneRiseSteps))
            #                 else: #otherwise, SET, 'S' first in set/reset col
            #                     firstSetResetCol = list(['S'] * len(oneRiseSteps))
            #                     secondSetResetCol = list(['R'] * len(oneRiseSteps))
            #                 setResetCol = pd.Series((firstSetResetCol + secondSetResetCol) * \
            #                                         self.canvas.cycleNumber.get() * combinationCount) #create a Pandas Series with 'S' for SET and 'R' for RESET
            #                 setResetCol.name = 'Set or Reset' #add a column name to the new setResetCol
            #                 results.loc[results['cycle'] != 0, 'Set or Reset'] = setResetCol.values # add SET/RESET column to results dataFrame
            #                 setResetCol = results.pop('Set or Reset') # move to proper position
            #                 results.insert(3, 'Set or Reset', setResetCol)
                        
            #             StepsData.name = 'Steps' #add a column name to the new StepsData
            #             results.loc[results['cycle'] != 0, 'Steps'] = StepsData.values # add it to the dataframe
            #             # depending on which read will be used for the step measurements, put the steps before it
            #             stepCol = results.pop('Steps')
            #             if (self.canvas.stepVoltageDirection.get() == 'Rise then Fall'): # RISE THEN FALL, both reads will be used
            #                 results.insert(4, 'Steps', stepCol)
            #             elif (self.canvas.chosenStepVoltage.get() == 'SET'):  # SET, read 1 will be used
            #                 results.insert(3, 'Steps', stepCol)
            #             else:   # RESET, read 2 will be used
            #                 results.insert(5, 'Steps', stepCol)

            # #create the .csv file with the base data information without
            # #special grid formatting here (special grid formatting done further down)
            # self.csvMgr.export_to_csv(results.copy(), info_lines, self.canvas)

            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            #from here, create another .csv file with the 64 x 64 grid information based on
            #the chosen modeState

            match self.canvas.modeState.get():

                case 'pulse_test':
            
                    if self.canvas.utilizeCurResRange.get():
                        self.csvMgr.makeRangeGridCsv(results.copy(), info_lines, self.canvas)

                    else:
                        self.csvMgr.makeGridCsv(results.copy(), info_lines, self.canvas)

                case 'pulse_step_test':

                    #since makeRangeGridCsv already addresses having multiple steps within
                    #a given range per cycle, makeRangeGridCsv was used instead of recreating
                    #makeGridCsv with a Pulse Step Test focus
                    self.csvMgr.makeRangeGridCsv(results.copy(), info_lines, self.canvas)

                case 'pulse_cycle_test':

                    #since makeRangeGridCsv can handle two runs of Pulse Tests while makeGridCsv
                    #cannot, makeRangeGridCsv was chosen
                    self.csvMgr.makeRangeGridCsv(results.copy(), info_lines, self.canvas)

                case 'iv_test':

                    #since makeRangeGridCsv already addresses having multiple steps within
                    #a given range per cycle, makeRangeGridCsv was used instead of recreating
                    #makeGridCsv with a Pulse Step Test focus
                    self.csvMgr.makeRangeGridCsv(results.copy(), info_lines, self.canvas)
        
    def exportRetentionData(self, cycle, result:pd.DataFrame):
        def worker():
            info_lines = self.csvMgr.getInfoLines(self.canvas)
            # self.csvMgr.export_to_csv(result.copy(), info_lines, self.canvas)
            self.csvMgr.safeRetentionResult(result.copy(), cycle, info_lines, self.canvas)

        workerThread = threading.Thread(target=worker)
        workerThread.start()

    # this function is unused, retention tests go to createPulseTestPlots
    # def createdRetentionPulseTestPLots(self, data:pd.DataFrame):
    #     if self.canvas.createSavePlots.get():

    #         print("\nMaking New Scatter Plot ...\n") if self.debug else None

    #         data = self.getData(self.canvas.toggledOhmsLawUnit.get())

    #         try:
    #             # Group by unique devices (row, col)
    #             for (row, col), group in data.groupby(['row', 'col']):
    #                 device = f"({row}-{col})"
    #                 read1 = None
    #                 read2 = None

    #                 try:
    #                     # Extract Read1 and Read2 time series per device over cycles
    #                     if 'Read1' in group.columns:
    #                         read1_values = group[['cycle', 'Read1']].set_index('cycle').sort_index()
    #                         read1 = (f"{device}", read1_values)

    #                     if 'Read2' in group.columns:
    #                         read2_values = group[['cycle', 'Read2']].set_index('cycle').sort_index()
    #                         read2 = (f"{device}", read2_values)
                        
    #                     with self.plotDataLock:
    #                         self.plotDataDict[device] = {'Read1': read1, 'Read2': read2}
    #                         self.newPlotDataEvent.set()

    #                 except Exception as e:
    #                     print(f"Error processing device {device}: {e}")
    #                     print(f"group: {group}")
    #                     self.stopEvent.set()
    #                     self.errorEvent.set()

    #         except Exception as e:
    #             print(f"General Error: {e}")
    #             self.stopEvent.set()
    #             self.errorEvent.set()
            
    #         print("updating plots ...") if self.debug else None

    #     if self.canvas.createHeatMap.get():
    #         print("\nMaking New Heat Map ...\n") if self.debug else None
            
    #         fullIndex = range(64)
    #         for cycle, group in data.groupby('cycle'):
    #             read1 = None
    #             read2 = None
    #             grid_read1 = pd.DataFrame()
    #             grid_read2 = pd.DataFrame()
    #             # Pivot read1 and read2 into grids
    #             try:
    #                 if 'Read1' in data.columns:
    #                     # Create a pivot table of the data, with the row and column indices
    #                     # sorted by their integer values
    #                     grid_read1 = group.pivot(index='row', columns='col', values='Read1')
    #                     grid_read1 = grid_read1.sort_index().sort_index(axis=1)
    #                     grid_read1 = grid_read1.reindex(index=fullIndex, columns=fullIndex)
        
    #                     # Optional: Replace missing entries explicitly with NaN
    #                     grid_read1 = grid_read1.astype('float')  # ensure it's float dtype with NaNs allowed
    #                     read1 = (f"Read1 - Cycle {cycle}", grid_read1)
                        
    #                 if 'Read2' in data.columns:
    #                     # Create a pivot table of the data, with the row and column indices
    #                     # sorted by their integer values
    #                     grid_read2 = group.pivot(index='row', columns='col', values='Read2')
    #                     grid_read2 = grid_read2.sort_index().sort_index(axis=1) 
    #                     grid_read2 = grid_read2.reindex(index=fullIndex, columns=fullIndex)
                        
    #                     # Optional: Replace missing entries explicitly with NaN
    #                     grid_read2 = grid_read2.astype('float')  # ensure it's float dtype with NaNs allowed

    #                     read2 = (f"Read2 - Cycle {cycle}", grid_read2)

    #                 with self.plotDataLock:
    #                     self.plotDataDict[cycle] = {'Read1':read1, 'Read2':read2}
    #                     self.newPlotDataEvent.set()
    #             except Exception as e:
    #                 print(f"Error: {e}")
    #                 print(f"group: {group}")
    #                 self.stopEvent.set()
    #                 self.errorEvent.set()
             
    def createRangePulseTestPLots(self):
        if self.canvas.createSavePlots.get():
            print("\nMaking New Scatter Plot ...\n") if self.debug else None

            data = self.getData(self.canvas.toggledOhmsLawUnit.get())

            try:
                # Group by unique devices (row, col)
                for (row, col), group in data.groupby(['row', 'col']):
                    device = f"({row}-{col})"
                    read1 = None
                    read2 = None

                    try:
                        # Extract Read2 time series per device over cycles
                        read2_values = group[['cycle', 'Read2']].set_index('cycle').sort_index()
                        # adjust index here so that each x location only has one y
                        rangeCycles = range(1, (1 + self.canvas.pulseTestRangeCycleCount.get()) * \
                                                (1 + self.canvas.pulseTestRangeCycleCount.get()) + 1)
                        read2_values.index = rangeCycles[:len(read2_values)]
                        read2 = (f"{device}", read2_values)

                        # if the device is in LRS, the data must go in read1
                        # because otherwise, it will be displayed as an HRS device in the plots
                        if group['status'].isin(['LRS']).any():
                            read1 = read2
                            read2 = None
                        # if it's HRS, read1 only contains the device data and not the reads,
                        #  so that UpdatePlots can run but only adds read2 data
                        else:
                            read1 = (f"{device}", pd.DataFrame())
                        
                        with self.plotDataLock:
                            self.plotDataDict[device] = {'Read1': read1, 'Read2': read2}
                            self.newPlotDataEvent.set()

                    except Exception as e:
                        print(f"Error processing device {device}: {e}")
                        print(f"group: {group}")
                        self.stopEvent.set()
                        self.errorEvent.set()

            except Exception as e:
                print(f"General Error: {e}")
                self.stopEvent.set()
                self.errorEvent.set()
            
            print("updating plots ...") if self.debug else None
        
        if self.canvas.createHeatMap.get():
            print("Making New Heat Map ...") if self.debug else None
            data = self.getData(self.canvas.toggledOhmsLawUnit.get())
            # Ensure 'cycle' is numeric
            data['cycle'] = pd.to_numeric(data['cycle'], errors='coerce')

            # Find index of the last cycle per (row, col) and put those rows into
            # a new Dataframe
            group = data.groupby(['row', 'col'], as_index=False).last().reset_index(drop=True)

            # Select those rows
            #group:pd.DataFrame = data.loc[idx].reset_index(drop=True)
            read1 = read2 = None
            fullIndex = range(64)
            try:
                # Pivot read1 and read2 into grids
                if 'Read1' in data.columns:
                    # Create a pivot table of the data, with the row and column indices
                    # sorted by their integer values
                    grid_read1 = group.pivot(index='row', columns='col', values='Read1')
                    grid_read1 = grid_read1.sort_index().sort_index(axis=1)
                    grid_read1 = grid_read1.reindex(index=fullIndex, columns=fullIndex)

                    # Optional: Replace missing entries explicitly with NaN
                    grid_read1 = grid_read1.astype('float')  # ensure it's float dtype with NaNs allowed
                    read1 = (f"Read1 - Final Cycle - {self.canvas.toggledOhmsLawUnit.get()}", grid_read1)
                    
                if 'Read2' in data.columns:
                    # Create a pivot table of the data, with the row and column indices
                    # sorted by their integer values
                    grid_read2 = group.pivot(index='row', columns='col', values='Read2')
                    grid_read2 = grid_read2.sort_index().sort_index(axis=1) 
                    grid_read2 = grid_read2.reindex(index=fullIndex, columns=fullIndex)
                    
                    # Optional: Replace missing entries explicitly with NaN
                    grid_read2 = grid_read2.astype('float')  # ensure it's float dtype with NaNs allowed

                    read2 = (f"Read2 - Final Cycle - {self.canvas.toggledOhmsLawUnit.get()}", grid_read2)

                with self.plotDataHeatMapLock:
                    self.plotDataDictHeatMap['Final'] = {'Read1':read1, 'Read2':read2}
                    self.newPlotDataEventHeatMap.set() 
            except Exception as e:
                        print(f"Error: {e}")
                        print(f"group: {group}")
                        self.stopEvent.set()
                        self.errorEvent.set()



# --------------------------------------------------------------------------------------------------
                                # UTILS FUNCTIONS
# ----------------------------------------------------------------------------------------------------

    def init_newRow(self, output):
        return {"row": output[0], "col": output[1], "cycle": output[2]}
    
    def init_AllDevices_newRow(self, output):
        return {"row": output[0], "col": output[1], "cycle": output[2], "status": output[4]}
    
    def init_gateVoltage_newRow(self, output):
        return {"row": output[0], "col": output[1], "cycle": output[2], "Gate Voltage": output[4]/1000}
    
    def init_rangeVerify_newRow(self, output):
        return {"row": output[0], "col": output[1], "cycle": output[2], "status": output[4]}
    
    def init_levelVerify_newRow(self, output):
        return {"row": output[0], "col": output[1], "cycle": output[2], "level": output[4], "Gate Voltage": output[5]/1000}
    
    def get_neighbors_even(self, row, col, grid_size=64, anchor="top-left"):
        """
        Return list of (r, c) indices for neighbors around (row, col)
        for an EVEN kernel size (e.g., 2, 4, 6).
        
        Args:
            row (int): row index of the anchor pixel
            col (int): column index of the anchor pixel
            kernelSize (int): size of the kernel (must be even)
            grid_size (int): size of grid (default 64)
            anchor (str): "top-left" (default) or "center"
        
        Returns:
            List of (row, col) tuples for neighbors inside the grid
        """
        if self.kernelSize % 2 != 0:
            raise ValueError("Kernel size must be even (2, 4, 6, ...)")
        
        neighbors = []
        
        if anchor == "top-left":
            start_r, start_c = row, col
        elif anchor == "center":
            # anchor is treated as the top-left of the 2x2 center block
            start_r, start_c = row - (self.kernelSize // 2 - 1), col - (self.kernelSize // 2 - 1)
        else:
            raise ValueError("Anchor must be 'top-left' or 'center'")
        
        for r in range(start_r, start_r + self.kernelSize):
            for c in range(start_c, start_c + self.kernelSize):
                if 0 <= r < grid_size and 0 <= c < grid_size:
                    neighbors.append((r, c))
        
        return neighbors
    

    def get_neighbors_odd(self, row, col, grid_size=64):
        """
        Return list of (r, c) indices for neighbors around (row, col)
        depending on kernel size.
        
        Args:
            row (int): row index of the pixel (0..grid_size-1)
            col (int): column index of the pixel (0..grid_size-1)
            kernelSize (int): size of kernel (must be odd, e.g., 3, 5, 7)
            grid_size (int): size of grid (default 64)
        
        Returns:
            List of (row, col) tuples for neighbors inside the grid
        """
        if self.kernelSize % 2 == 0:
            raise ValueError("Kernel size must be odd (3, 5, 7, ...)")
        
        half_k = self.kernelSize // 2
        neighbors = []
        
        for r in range(row - half_k, row + half_k + 1):
            for c in range(col - half_k, col + half_k + 1):
                neighbors.append((r, c))
        
        return neighbors

    def readLines(self, expectedDelay, lines=[], delayIdx=0, trier=0):
        # Send the input command
        start = int(time.perf_counter() * 1e6)
        pref = int(time.perf_counter() * 1e6)
        while (pref - start) < expectedDelay[delayIdx]:
            if self.cmd.inWaiting() > 0:
                line = self.cmd.readline()
                if line:
                    lines.append(line.strip())
                    delayIdx += 1
                    if delayIdx >= len(expectedDelay):
                        return lines
                    start = int(time.perf_counter() * 1e6)
            pref = int(time.perf_counter() * 1e6)
        else:
            return self.readLines(expectedDelay, lines, delayIdx, trier+1)
    
    def getValues(self, lines: list[str]):
        """
        Processes the output lines to extract channel data and current readings.

        Args:
            lines (list of str): The lines of data from the output.
            unit (str): The unit for the current value, either 'uA' or 'kOhm'. Defaults to 'uA'.

        Returns:
            dict: A dictionary where keys are read names (e.g., 'Read1', 'Read2') and values are
                  dictionaries containing 'Channel' and 'Value' for each read.
        """
        reads = {}

        for line in lines:
            # Skip lines that are only 'R' or 'S'
            if line in ['R', 'S']: 
                continue 

            try:
                # Split the line into channel and current value
                channel, curr = line.split(';')
                channel = channel.strip('Ch:')
                
                # Extract current name and value
                currName, currValue = curr.split('= ')
                currName = currName.strip()
                if '0.-1' in currValue:
                    currValue = '0'

                # Determine which voltage to use based on current name
                i = 0 if 'I1' in currName else 1

                # Convert the current value to the appropriate unit
                value = float(currValue.strip()) 
                # Store the extracted data in the reads dictionary
                reads['Read' + str(i + 1)] = {'Channel': channel, 'Value': value}

            except (ValueError, TypeError):
                # Skip lines that cannot be processed (Header lines)
                continue

        return reads

    #--------------------------------------------------------------------------------------

    #function to address the unique format of the IV test outputs that the getValues function
    #is not built to handle
    #extract the voltage and current information from the inputted output lines, which
    #returns the dictionary to be used in processOutputIVTest
    #NOTE: 1.1 IV Test output format (with each line be printed PER STEP)
    ##(when rising) RISING-Read1 V = # mV ; I = # uA
    #(when falling) FALLING-Read1 V = # mV ; I = # uA
    def getValuesIV(self, lines: list[str]):

        reads = {} #initialize the dictionary to be outputted

        for line in lines:
            
            try:

                #before extracting the numbers as floats, remove the
                #first number used strictly for aesthetic that Jeelka chose
                #to include in the format alongside the "Read" string

                ReadStringIndex = line.find('Read') #find the character index of where the "Read" string BEGINS

                #prepare to get the full "Read#" string and remove it using string character index logic
                readNumberIndexEnd = ReadStringIndex + len('Read') + 1 #get the ending character index for the "Read#"

                readNumberString = line[ReadStringIndex:readNumberIndexEnd]

                #concatenate a new string that removes the "Read#" strng from within the initial "line" above
                formattedLine = line[:ReadStringIndex] + line[readNumberIndexEnd:]
                line = formattedLine

                # - - - - - - - - - - - - - - - - - - - - - -

                #find and extract all floats within the "line"

                numberRegularExpressionPattern = r"[-+]?\d*\.?\d+" #create integer/float format with varying numbers within the whole number/decimal places

                extractedFloatStrings = re.findall(numberRegularExpressionPattern, line) #find all floats as strings

                #convert the number strings to floats, with the FIRST one based on the format provided
                #being the VOLTAGE and the second value being the CURRENT
                lineVoltage, lineCurrent = [float(floatString) for floatString in extractedFloatStrings]

                #store the voltage, current AND state/direction within the reads dictionary
                #NOTE: to avoid any dictionaries having the same keys get overwritten, check if
                #the key is already made and simply append to it if it already exists on repeat runs
                if(readNumberString in reads): #if readNumberString key already exists
                    reads[readNumberString]['Voltage'].append(lineVoltage)
                    reads[readNumberString]['Current'].append(lineCurrent)
                    if('RISING' in line):
                        reads[readNumberString]['State'].append('RISING')
                    elif('FALLING' in line):
                        reads[readNumberString]['State'].append('FALLING')
                else: #otherwise, create readNumberString key
                    if('RISING' in line):
                        reads[readNumberString] = {'Voltage': [lineVoltage], 'Current': [lineCurrent], 'State': ['RISING']}
                    elif('FALLING' in line):
                        reads[readNumberString] = {'Voltage': [lineVoltage], 'Current': [lineCurrent], 'State': ['FALLING']}

            except (ValueError, TypeError):
                # Skip lines that cannot be processed (Header lines)
                continue

        return reads

    #--------------------------------------------------------------------------------------

    def getExpectedDelay(self, canvas:BaseCanvas):
        # if anything changes here, check that processInputPulseStepTest doesn't also need those changes
        # places where delay is changed there: 2x in the 1st 'if', 3x in the 'else' after it, and
        # 1x in the second rising operation

        offset = 100 # us
        delayList = []
        delayTime = canvas.delayPeriodTime.get()

        if canvas.formSetVoltage.get() != 0:
            delayList.append(canvas.formSetTime.get() + delayTime + offset)

        if canvas.formSetReadVoltage.get() != 0:
            delayList.append(canvas.formSetReadTime.get() + delayTime + offset)

        if canvas.resetVoltage.get() != 0:
            delayList.append(canvas.resetTime.get() + delayTime + offset)

        if canvas.resetReadVoltage.get() != 0:
            delayList.append(canvas.resetReadTime.get() + delayTime + offset)

        return delayList
