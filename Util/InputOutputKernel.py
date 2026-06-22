from typing import Callable
import threading
import queue
import time

from pandas import DataFrame
from GUI import BaseCanvas
import copy

class InOutKernel:
    def __init__(self, debug=False):
        self.debug = debug

        self.results = None
        self.progress = 0

        self.inputTarget:Callable = None
        self.outputTarget:Callable = None
        self.executeTarget:Callable = None
        self.finishTarget:Callable = None

        self.inputQueue = queue.Queue()
        self.outputQueue = queue.Queue()

        self.results_lock = threading.Lock()
    
        self.errorEvent = threading.Event()
        self.newOutputEvent = threading.Event()

        self.stopEvent = threading.Event()  # for clean exit
        self.inputDoneEvent = threading.Event()
        self.inputThreadDoneEvent = threading.Event()
        self.outputThreadDoneEvent = threading.Event()
        self.newPlotDataEvent = threading.Event()
        self.newPlotDataEventHeatMap = threading.Event()

        self.stopEvent.set()
        self.inputDoneEvent.set()


    
    def start(self):
        """
        Start the input and output threads. Make sure to call `init` first to set the canvas.
        """
        self.stopEvent.clear()
        self.errorEvent.clear()
        self.newOutputEvent.clear()

        self.inputDoneEvent.clear()
        self.inputThreadDoneEvent.clear()
        self.outputThreadDoneEvent.clear()
        self.newPlotDataEvent.clear()
        self.newPlotDataEventHeatMap.clear()

        self.inputQueue.queue.clear()
        self.outputQueue.queue.clear()

        self.progress = 0
        # This variable is used to decide wither to do SET or RESET when range without allDevices is selected.
        # SEE: InputOutputManager.init 
        # SEE: InputOutputKernel.addRangeInput
        self.deviceStat = None 

        self.inputThread = threading.Thread(target=lambda:self.checkInputQueue(self.inputTarget))
        self.outputThread = threading.Thread(target=lambda:self.checkOutputQueue(self.outputTarget))
        self.executeThread = threading.Thread(target=lambda:self.executeOutput(self.executeTarget, self.finishTarget))

        self.inputThread.start()
        self.outputThread.start()
        self.executeThread.start()
    
    def inputDone(self):
        self.inputDoneEvent.set()
    
    def hardStop(self):
        self.inputDoneEvent.set()
        self.inputThreadDoneEvent.set()
        self.outputThreadDoneEvent.set()
        self.newPlotDataEvent.clear()
        self.newPlotDataEventHeatMap.clear()
        self.stopEvent.set()
        self.errorEvent.set()

    def join(self):
        self.inputThread.join()
        self.outputThread.join()

    def resetResults(self):
        with self.results_lock:
            self.results:DataFrame = DataFrame()

    def inUse(self):
        return not self.stopEvent.is_set()
    
    def isError(self):
        return self.errorEvent.is_set()
    
    def isRunning(self):
        return not self.stopEvent.is_set()
    
    def isDone(self):
        return self.stopEvent.is_set()
    
    def isInputDone(self):
        return self.inputDoneEvent.is_set()
    
    def isInputThreadDone(self):
        return self.inputThreadDoneEvent.is_set()
    
    def isOutputThreadDone(self):
        return self.outputThreadDoneEvent.is_set()
    
    def isOutputDone(self):
        return self.outputThreadDoneEvent.is_set()
    

    
    def isSuccessful(self):
        return self.stopEvent.is_set() and not self.errorEvent.is_set()
    
    def getResults(self) ->DataFrame:
        with self.results_lock:
            return copy.deepcopy(self.results)

    # def addAllDeviceInput(self, row, col, byteList, deviceStat, cycle=1):
    #     self.inputQueue.put([row, col, cycle, byteList, deviceStat])  # cycle = 1

    def addInput(self, row, col, byteList, cycle=1):
        self.inputQueue.put([row, col, cycle, byteList])   
    
    def addDeviceStatInput(self, row, col, byteList, deviceStat=True, cycle=1):
        self.inputQueue.put([row, col, cycle, byteList, deviceStat])

    def addDeviceLevelInput(self, row, col, byteList, deviceLevel, gateVoltage, cycle=1):
        self.inputQueue.put([row, col, cycle, byteList, deviceLevel, gateVoltage])

    def addGateRangeInput(self, row, col, byteList, gateVoltage, cycle=1):
        self.inputQueue.put([row, col, cycle, byteList, gateVoltage])  


    
    def checkInputQueue(self, callback:callable):
        while not self.stopEvent.is_set():
            try:
                item = self.inputQueue.get(timeout=0.1)
                callback(item)
            except queue.Empty:
                if self.inputDoneEvent.is_set():
                    self.inputThreadDoneEvent.set()
                    print("input thread done") if self.debug else None
                    break
                else: 
                    print("waiting for input ...") if self.debug else None
                    continue
    
    def checkOutputQueue(self, callback:callable):
        while not self.stopEvent.is_set():
            try:
                item = self.outputQueue.get(timeout=0.1)
                callback(item)
                self.newOutputEvent.set()
            except queue.Empty:
                if self.inputThreadDoneEvent.is_set():
                    # Queue is empty and input is done, stop the threads.
                    print("output thread done") if self.debug else None
                    self.outputThreadDoneEvent.set()
                    break
                else: 
                    print("waiting for output ...") if self.debug else None
                    continue


    def executeOutput(self, callback:Callable, finishCallback:Callable = None):
        while not self.stopEvent.is_set():
            if self.newOutputEvent.is_set() and not (self.newPlotDataEvent.is_set() or \
                                                     self.newPlotDataEventHeatMap.is_set()):
                self.newOutputEvent.clear()
                callback()
            else:
                if self.outputThreadDoneEvent.is_set():
                    print("executing output done ...") if self.debug else None
                    self.stopEvent.set()
                    break
                else: 
                    time.sleep(0.5)
                    # print("waiting for new output ...") if self.debug else None
                    
        if not self.errorEvent.is_set():
            finishCallback()
