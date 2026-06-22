import serial
import serial.tools.list_ports
import time

class SerialPort:

    def __init__(self, portName, baudRate = 115200, timeout = 1):
        self.portName = portName #'Silicon Labs CP210x'
        self.port = self.findPort(self.portName)
        self.baudRate = baudRate
        self.timeout = timeout

        #set the serial native port device (class)
        self.cmd: serial.Serial = serial.Serial(self.port, baudRate, timeout = timeout, \
                                    bytesize = serial.EIGHTBITS) # Define serial device
        
        
    def write(self, data):
        self.cmd.write(data)
    
    def read(self, size=1):
        return self.cmd.read(size).decode('utf-8')
    
    def readline(self, terminator = b'\r\n'):
        buf = bytearray()
        while True:
            ch = self.cmd.read(1)
            if not ch:
                break
            buf += ch
            if buf.endswith(terminator):
                break
        return bytes(buf).decode('utf-8', errors='ignore').strip('\r\n')
        # return self.cmd.readline().decode('utf-8').strip('\r\n')

    def resetBuffer(self):
        self.cmd.reset_input_buffer()
        
    def inWaiting(self):
        return self.cmd.in_waiting
    
    def updateTimeOut(self, timeout):
        was_open = self.cmd.is_open
        if was_open:
            self.cmd.close()
        self.cmd.timeout = timeout
        if was_open:
            self.cmd.open()
    
    def close(self):
        self.cmd.close()
    
    def isOpen(self):
        return self.cmd.is_open
    
    def flush(self):
        self.cmd.flush()
    
    def reConnect(self):
        try:
            self.cmd.close()
            self.cmd.open()
            return True
        except:
            return False

    def findPort(self, portName):
        """
        Searches through available serial ports and returns the device name/path of the port
        that matches the expected port information.

        Args:
            portName: An object with a 'get' method that returns a string
                                    representing the expected port information.

        Returns:
            A string representing the device name/path of the desired port if found,
            otherwise returns None.
        """

        portsList = serial.tools.list_ports.comports()
        
        #initialize empty "ListPortInfo" object to return the found (desired) port
        desiredPortInfo = None

        #search for the desired port among all the ports obtained above
        for currentPort in portsList:

            #perform the search by converting the "ListPortInfo" object into a string
            portString = str(currentPort)

            #if the expected port information is within the current port string
            if portName in portString:
                
                #split the found port string information up with the space delimiter
                splitDesiredPortInfo = portString.split(' ')
                
                #get the device name/path (first object element in "ListPortInfo")
                #in string format from the split port string above
                desiredPortInfo = splitDesiredPortInfo[0]
                break

        #return desired port information
        return desiredPortInfo
    