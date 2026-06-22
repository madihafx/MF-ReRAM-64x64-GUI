
from GUI.BaseCanvas import BaseCanvas
import pandas as pd
import os, re, csv, datetime

class CsvManager:
    def __init__(self, debug = False):
        self.debug = debug
        self.folderDirectory = None

    def export_to_csv(self, data:pd.DataFrame, infoLines:list, canvas:BaseCanvas):
        if not self.folderDirectory:
            self.setDataDirectory(canvas.saveDirectory.get(), canvas.saveFileName.get())

        print(f"Saving to {self.folderDirectory}") if self.debug else None

        # - - - - - - - - - - - - - - - - - -

        #at Jeelka's request, each device for an IV Test will be given a dedicated
        #.csv file
        if(canvas.modeState.get()== 'iv_test'): #for an IV test, split up the data by device

            #NOTE: Each selected device will be chosen by each UNIQUE COMBINATION of the rows and columns
            rowColCombinations = data.groupby(['row', 'col'])
            rowColCombinationsList = list(rowColCombinations.groups.keys())

            # adjust the columns names and save to a CSV file
            self.setColumnsNames(data, canvas)

            for row, col in rowColCombinationsList:
                
                #create a new filePath with the device row column information
                #while also getting the data for that specific device inputted into
                #the "toCsv" function
                filePath = os.path.join(self.folderDirectory, f'data_deviceR{row}_C{col}.csv')
                singleDeviceData = data[(data['row'].astype(int) == row) & (data['col'].astype(int) == col)]
                self.singleToCsv(filePath, singleDeviceData, infoLines)

            
        else: #otherwise, proceed to do a single .csv file for all devices selected

            # adjust the columns names and save to a CSV file
            self.setColumnsNames(data, canvas)
            self.splitToCsv(data, infoLines)


    # writes to CSV files, splitting into multiple if over 1,000,000 rows
    def splitToCsv(self,  data:pd.DataFrame, infoLines:list,*, index_label=None):
        dataRows = len(data) # only data rows matter for the calculation, because there are so few infoLines rows they will still fit
        totalFiles = - (-dataRows // 1000000) # 1,000,000 row maximum to be easily within Excel limits (& allow for infoLines)

        for i in range(totalFiles):
            startRow = i * 1000000
            endRow = min(startRow + 1000000, dataRows)
            chunk = data.iloc[startRow:endRow]

            fileName = f"dataOld_{i+1}.csv"
            filePath = os.path.join(self.folderDirectory, fileName)
            with open(filePath, 'w') as file:
                for line in infoLines:
                    file.write('# ' +line + "\n")
                file.write('\n')

                # Write CSV header
                header = [index_label] + list(data.columns) if index_label else list(data.columns)
                file.write(','.join(str(h) for h in header) + '\n')

                # Write rows manually
                for idx, row in chunk.iterrows():
                    values = [str(idx)] if index_label else []
                    for val in row:
                        if pd.isna(val):  # or: math.isnan(val) if all values are floats
                            values.append('')
                        else:
                            values.append(str(val))
                    file.write(','.join(values) + '\n')


    def singleToCsv(self, filePath,  data:pd.DataFrame, infoLines:list,*, index_label=None):
        with open(filePath, 'w') as file:
            for line in infoLines:
                file.write('# ' +line + "\n")
            file.write('\n')

            # Write CSV header
            header = [index_label] + list(data.columns) if index_label else list(data.columns)
            file.write(','.join(str(h) for h in header) + '\n')

            # Write rows manually
            for idx, row in data.iterrows():
                values = [str(idx)] if index_label else []
                for val in row:
                    if pd.isna(val):  # or: math.isnan(val) if all values are floats
                        values.append('')
                    else:
                        values.append(str(val))
                file.write(','.join(values) + '\n')

        
    def makeGridCsv(self, data:pd.DataFrame, infoLines:list, canvas:BaseCanvas):

        
        """Create CSV files of the data in a grid format for each cycle.
        
        The CSV files are named in the format
        <filename>_cycle<cycle_number>_read1.csv or
        <filename>_cycle<cycle_number>_read2.csv
        
        The CSV files are stored in the directory specified by the `directory` argument.
        """
        if canvas.modeState.get() == 'iv_test':
            return

        if not self.folderDirectory:
            self.setDataDirectory(canvas.saveDirectory.get(), canvas.saveFileName.get())

        print("---------------------------------------------------------------") if self.debug else None
        
        fullIndex = range(64) 

        read1_dir = None
        read2_dir = None
        for cycle, group in data.groupby('cycle'):
            # Pivot Read1 and Read2 into grids
            # print(data.columns) # commented out because it was getting annoying
            if 'Read1' in data.columns:
                if not read1_dir:
                    read1_dir = os.path.join(self.folderDirectory, 'Read1')
                    os.makedirs(read1_dir, exist_ok=True)
                
                # Create a pivot table of the data, with the row and column indices
                # sorted by their integer values
                grid_read1 = group.pivot(index='row', columns='col', values='Read1')
                grid_read1 = grid_read1.sort_index().sort_index(axis=1)
                grid_read1 = grid_read1.reindex(index=fullIndex, columns=fullIndex)

                i1_filename = os.path.join(read1_dir, 
                                f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle})_read1.csv')
                i = 1
                # check if the file already exists, this will only happen on retention test.
                while os.path.exists(i1_filename):
                    i1_filename = os.path.join(read1_dir, 
                                f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle+i})_read1.csv')
                    i += 1

                self.singleToCsv(i1_filename, grid_read1, infoLines, index_label='row')

                # if canvas.toggledOhmsLawUnit.get() != 'uA':
                #     # Create a pivot table of the data, with the row and column indices
                #     # sorted by their integer values
                #     grid_i1 = group.pivot(index='row', columns='col', values='Read1 (uA)')
                #     grid_i1 = grid_i1.sort_index().sort_index(axis=1)
                #     grid_i1 = grid_i1.reindex(index=fullIndex, columns=fullIndex)

                #     i1_filename = os.path.join(read1_dir, 
                #                     f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle})_read1_uA.csv')
                #     i = 1
                #     while os.path.exists(i1_filename):
                #         i1_filename = os.path.join(read1_dir, 
                #                     f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle+i})_read1_uA.csv')
                #         i += 1
                    
                #     self.toCsv(i1_filename, grid_i1, infoLines, index_label='row')


                print(f"Cycle {cycle}: saved {i1_filename}") if self.debug else None
                
            if 'Read2' in data.columns:
                if not read2_dir:
                    read2_dir = os.path.join(self.folderDirectory, 'Read2')
                    os.makedirs(read2_dir, exist_ok=True)

                # Create a pivot table of the data, with the row and column indices
                # sorted by their integer values
                grid_read2 = group.pivot(index='row', columns='col', values='Read2')
                grid_read2 = grid_read2.sort_index().sort_index(axis=1) 
                grid_read2 = grid_read2.reindex(index=fullIndex, columns=fullIndex)

                i2_filename = os.path.join(read2_dir, 
                                f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle})_read2.csv')
                i = 1
                while os.path.exists(i2_filename):
                    i2_filename = os.path.join(read2_dir, 
                                f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle+i})_read2.csv')
                    i += 1

                self.singleToCsv(i2_filename, grid_read2, infoLines, index_label='row')

                # if canvas.toggledOhmsLawUnit.get() != 'uA':
                #     # Create a pivot table of the data, with the row and column indices
                #     # sorted by their integer values
                #     grid_i2 = group.pivot(index='row', columns='col', values='Read2 (uA)')
                #     grid_i2 = grid_i2.sort_index().sort_index(axis=1)
                #     grid_i2 = grid_i2.reindex(index=fullIndex, columns=fullIndex)

                #     i2_filename = os.path.join(read2_dir, 
                #                     f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle})_read2_uA.csv')
                #     i = 1
                #     while os.path.exists(i2_filename):
                #         i2_filename = os.path.join(read2_dir, 
                #                     f'{canvas.saveFileName.get()}_grid_64x64_cycle({cycle+i})_read2_uA.csv')
                #         i += 1
                    
                #     self.toCsv(i2_filename, grid_i2, infoLines, index_label='row')
                print(f"Cycle {cycle}: saved {i2_filename}") if self.debug else None


    def makeRangeGridCsv(self, data:pd.DataFrame, infoLines:list, canvas:BaseCanvas):
        # Ensure 'cycle' is numeric
        data['cycle'] = pd.to_numeric(data['cycle'], errors='coerce')

        #NOTE: if performing the "pulse_cycle_test", where there are two rows for the data
        #of the same cycle where the voltage that isn't under test for the SET or RESET runs
        #returning NaNs, use bfill to backwards fill the NaNs with the next value propogations
        #to combine the two outputs onto the same line for the next lines of code to handle it
        if(canvas.modeState.get() == 'pulse_cycle_test'):
            backFilledData = data.bfill()

        # find the most recent cycle per (row, col) if range verification is used
        # this is because in HRS mode, the cycles may restart within the same device, because
        # of the way the changing RESET voltage is implemented
        if canvas.utilizeCurResRange.get():
            group = data.groupby(['row', 'col']).tail(1).reset_index(drop=True)
        else:
            # Find index of the largest cycle per (row, col)
            idx = data.groupby(['row', 'col'])['cycle'].idxmax()
            # Select those rows
            if(canvas.modeState.get() == 'pulse_cycle_test'):
                group:pd.DataFrame = backFilledData.loc[idx].reset_index(drop=True)
            else:
                group:pd.DataFrame = data.loc[idx].reset_index(drop=True)

        fullIndex = range(64) 

        if not self.folderDirectory:
            self.setDataDirectory(canvas.saveDirectory.get(), canvas.saveFileName.get())

        if 'Read1' in data.columns:
            read1_dir = os.path.join(self.folderDirectory, 'Read1')
            os.makedirs(read1_dir, exist_ok=True)

            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
            
            # Create a pivot table of the data, with the row and column indices
            # sorted by their integer values
            
            #NOTE: This "pivot table" provided by Quotayba is meant to show the full
            #64 x 64 grid and populate any device's dedicated Excel file cell (based on
            #row and column position) with the 'Read1' or 'Read2' values respectively as
            #a SEPARATE file from the "data" outputs above
            grid_read1 = group.pivot(index='row', columns='col', values='Read1')
            grid_read1 = grid_read1.sort_index().sort_index(axis=1)
            grid_read1 = grid_read1.reindex(index=fullIndex, columns=fullIndex)

            read1_filename = os.path.join(read1_dir,
                                          f"{canvas.saveFileName.get()}_grid_64x64_cycle(Final)_read1.csv")
            
            self.singleToCsv(read1_filename, grid_read1, infoLines, index_label='row')

            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            # if canvas.toggledOhmsLawUnit.get() != 'uA':
            #     grid_i1 = group.pivot(index='row', columns='col', values='Read1 (uA)')
            #     grid_i1 = grid_i1.sort_index().sort_index(axis=1)
            #     grid_i1 = grid_i1.reindex(index=fullIndex, columns=fullIndex)

            #     i1_filename = f"{canvas.saveFileName.get()}_grid_64x64_cycle(Final)_read1_uA.csv"

            #     self.toCsv(i1_filename, grid_i1, infoLines, index_label='row')

            print(f"Cycle Final: saved {read1_filename}") if self.debug else None
                
        if 'Read2' in data.columns:
            read2_dir = os.path.join(self.folderDirectory, 'Read2')
            os.makedirs(read2_dir, exist_ok=True)

            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
            
            # Create a pivot table of the data, with the row and column indices
            # sorted by their integer values

            #NOTE: This "pivot table" provided by Quotayba is meant to show the full
            #64 x 64 grid and populate any device's dedicated Excel file cell (based on
            #row and column position) with the 'Read1' or 'Read2' values respectively as
            #a SEPARATE file from the "data" outputs above
            grid_read2 = group.pivot(index='row', columns='col', values='Read2')
            grid_read2 = grid_read2.sort_index().sort_index(axis=1) 
            grid_read2 = grid_read2.reindex(index=fullIndex, columns=fullIndex)

            read2_filename = os.path.join(read2_dir, 
                                          f"{canvas.saveFileName.get()}_grid_64x64_cycle(Final)_read2.csv")
            
            self.singleToCsv(read2_filename, grid_read2, infoLines, index_label='row')

            # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

            # if canvas.toggledOhmsLawUnit.get() != 'uA':
            #     grid_i2 = group.pivot(index='row', columns='col', values='Read2 (uA)')
            #     grid_i2 = grid_i2.sort_index().sort_index(axis=1)
            #     grid_i2 = grid_i2.reindex(index=fullIndex, columns=fullIndex)

            #     i2_filename = f"{canvas.saveFileName.get()}_grid_64x64_cycle(Final)_read2_uA.csv"

            #     self.toCsv(i2_filename, grid_i2, infoLines, index_label='row')
            print(f"Cycle Final: saved {read2_filename}") if self.debug else None


    def safeRetentionResult(self, data:pd.DataFrame, cycle, infoLines:list, canvas:BaseCanvas):
        if not self.folderDirectory:
            self.setDataDirectory(canvas.saveDirectory.get(), canvas.saveFileName.get())
        
        retention_dir = os.path.join(self.folderDirectory, 'Retention')
        os.makedirs(retention_dir, exist_ok=True)

        retention_filename = os.path.join(retention_dir, f"{canvas.saveFileName.get()}_retention.csv")

        if not os.path.exists(retention_filename):
            header = ['cycle', 'Time'] + [f"Dev_({row}, {col})" for row in range(64) for col in range(64)]
            with open(retention_filename, 'a', newline='') as file:
                for line in infoLines:
                    file.write('# ' + line + "\n")
                file.write("\n")  # blank line

                writer = csv.writer(file)
                writer.writerow(header)
        
        if 'Read2' not in data.columns:
            return
        devices = [' ' for _ in range(64*64)]

        for i in range(len(data)):
            row = data.at[i, 'row']
            col = data.at[i, 'col']
            devices[row * 64 + col] = data.at[i, 'Read2']

        with open(retention_filename, 'a', newline='') as file:
            writer = csv.writer(file)
            row = [cycle, cycle*canvas.retentionTime.get()]
            row += devices
            writer.writerow(row)

        print(f"Retention: saved {retention_filename}") if self.debug else None


            
    def setColumnsNames(self, df:pd.DataFrame,  canvas:BaseCanvas):
        nameDict = {}
        if canvas.toggledOhmsLawUnit.get() == 'uA':
            if 'Read1' in df.columns:
                nameDict['Read1'] = 'Read1 (uA)'
            if 'Read2' in df.columns:
                nameDict['Read2'] = 'Read2 (uA)'
        else:
            if 'Read1' in df.columns:
                nameDict['Read1'] = 'Read1 (kOhm)'
            if 'Read2' in df.columns:
                nameDict['Read2'] = 'Read2 (kOhm)'

        if nameDict: 
            df.rename(columns=nameDict, inplace=True)
    

    def setDataDirectory(self, directory, filename=None):
        fileName = filename if filename else 'new_test'

        current_time = datetime.datetime.now()
        timestamp = current_time.strftime("%d-%m-%Y-%Hh_%Mm_%Ss")
        dir = os.path.join(directory, f"{fileName}_{timestamp}")
        os.makedirs(dir)
        self.folderDirectory = dir
        print("--------------------------- filename: ", self.folderDirectory)


    def getInfoLines(self, canvas:BaseCanvas):

        match canvas.modeState.get():
            case 'pulse_test':
                testName = 'Pulse Test'
            case 'pulse_step_test':
                testName = f'Pulse Step Test - {canvas.chosenStepVoltage.get()} {canvas.stepVoltageDirection.get()}'
            case 'pulse_cycle_test':
                if(canvas.invertIVStates.get()): #if inverted states, i.e. RESET/SET
                    testName = 'Pulse RESET/SET Switch Test'
                else: #otherwise, default SET/RESET
                    testName = 'Pulse SET/RESET Switch Test'
            case 'iv_test':
                testName = 'IV Test'
        
        formSetLabel = canvas.formSetStateString.get()
        if canvas.retentionTest.get():
            info_lines = [f'ReRAM 64x64 GUI Test: {testName}', f'Gate Voltage: {canvas.gateVoltage.get()}', 
                        f'{formSetLabel} Mode: {formSetLabel}',
                        f'Read2 Voltage: {canvas.resetReadVoltage.get()}', f'Read2 Time: {canvas.resetReadTime.get()}',
                        f'Delay Time: {canvas.delayPeriodTime.get()}', f'Number of Cycles: {canvas.cycleNumber.get()}', 
                        f'Steps per Direction: {canvas.stepNumber.get()}', f'Retention Time: {canvas.retentionTime.get()}']
            return info_lines

        # - - - - - - - - - - - - - - - - - - - - - - - - - - -

        if(canvas.modeState.get() == 'pulse_cycle_test'): #if SET/RESET switch, also include the gate RESET voltage
            info_lines = [f'ReRAM 64x64 GUI Test: {testName}', f'SET Gate Voltage: {canvas.gateVoltage.get()}',
                          f'RESET Gate Voltage: {canvas.gateCycleVoltage.get()}', f'{formSetLabel} Mode: {formSetLabel}',
                          f'{formSetLabel} Voltage: {canvas.formSetVoltage.get()}', f'{formSetLabel} Time: {canvas.formSetTime.get()}',
                          f'Reset Voltage: {canvas.resetVoltage.get()}', f'Read1 Voltage: {canvas.formSetReadVoltage.get()}',
                          f'Read1 Time: {canvas.formSetReadTime.get()}', f'Read2 Voltage: {canvas.resetReadVoltage.get()}',
                          f'Read2 Time: {canvas.resetReadTime.get()}', f'Delay Time: {canvas.delayPeriodTime.get()}',
                          f'Number of Cycles: {canvas.cycleNumber.get()}', f'Steps per Direction: {canvas.stepNumber.get()}',
                          f'Range Test: {canvas.utilizeCurResRange.get()}']


        elif(canvas.modeState.get() == 'iv_test'): #if IV Test, include which of the IV modes was selected in the title

            if(canvas.IvTestState.get() == 'IV'): #if unique IV mode that does both SET and RESET
                if(canvas.invertIVStates.get()): #add additional string for special IV mode if the order is inverted
                    orderString = 'RESET/SET'
                else:
                    orderString = 'SET/RESET'

                info_lines = [f'ReRAM 64x64 GUI Test: {testName} - {canvas.IvTestState.get()} Mode - {orderString}',
                              f'Gate Voltage: {canvas.gateVoltage.get()}', f'{formSetLabel} Mode: {formSetLabel}' ,
                              f'{formSetLabel} Voltage: {canvas.formSetVoltage.get()}', f'{formSetLabel} Time: {canvas.formSetTime.get()}',
                              f'Reset Voltage: {canvas.resetVoltage.get()}', f'Read1 Voltage: {canvas.formSetReadVoltage.get()}',
                              f'Read1 Time: {canvas.formSetReadTime.get()}', f'Read2 Voltage: {canvas.resetReadVoltage.get()}',
                              f'Read2 Time: {canvas.resetReadTime.get()}', f'Delay Time: {canvas.delayPeriodTime.get()}',
                              f'Number of Cycles: {canvas.cycleNumber.get()}', f'Steps per Direction: {canvas.stepNumber.get()}',
                              f'Range Test: {canvas.utilizeCurResRange.get()}']

            else: #otherwise, other three IV modes, ignore orderString

                info_lines = [f'ReRAM 64x64 GUI Test: {testName} - {canvas.IvTestState.get()} Mode',
                              f'Gate Voltage: {canvas.gateVoltage.get()}', f'{formSetLabel} Mode: {formSetLabel}' ,
                              f'{formSetLabel} Voltage: {canvas.formSetVoltage.get()}', f'{formSetLabel} Time: {canvas.formSetTime.get()}',
                              f'Reset Voltage: {canvas.resetVoltage.get()}', f'Read1 Voltage: {canvas.formSetReadVoltage.get()}',
                              f'Read1 Time: {canvas.formSetReadTime.get()}', f'Read2 Voltage: {canvas.resetReadVoltage.get()}',
                              f'Read2 Time: {canvas.resetReadTime.get()}', f'Delay Time: {canvas.delayPeriodTime.get()}',
                              f'Number of Cycles: {canvas.cycleNumber.get()}', f'Steps per Direction: {canvas.stepNumber.get()}',
                              f'Range Test: {canvas.utilizeCurResRange.get()}']
        
        elif canvas.utilizeCurResRange.get():
            if canvas.applyToAllDevices.get(): # if hard coding all devices, both rangeGateVoltage and rangeResetVoltage are needd
                info_lines = [f'ReRAM 64x64 GUI Test: {testName}', f'Gate Voltage: {canvas.gateVoltage.get()}', 
                                f'End Gate Voltage: {canvas.minGateVoltage.get()}',
                                f'{formSetLabel} Mode: {formSetLabel}' ,f'{formSetLabel} Voltage: {canvas.formSetVoltage.get()}', 
                                f'{formSetLabel} Time: {canvas.formSetTime.get()}', f'Reset Voltage: {canvas.resetVoltage.get()}',
                                f'End Reset Voltage: {canvas.minResetVoltage.get()}',
                                f'Read1 Voltage: {canvas.formSetReadVoltage.get()}', f'Read1 Time: {canvas.formSetReadTime.get()}',
                                f'Read2 Voltage: {canvas.resetReadVoltage.get()}', f'Read2 Time: {canvas.resetReadTime.get()}',
                                f'Delay Time: {canvas.delayPeriodTime.get()}', f'Number of Cycles: {canvas.cycleNumber.get()}', 
                                f'Steps per Direction: {canvas.stepNumber.get()}', f'Range Test: {canvas.utilizeCurResRange.get()}']
            elif canvas.hrsRangeMax.get() > 0: # if not hard coding and are doing HRS, rangeResetVoltage is needed
                info_lines = [f'ReRAM 64x64 GUI Test: {testName}', f'Gate Voltage: {canvas.gateVoltage.get()}', 
                                f'{formSetLabel} Mode: {formSetLabel}' ,f'{formSetLabel} Voltage: {canvas.formSetVoltage.get()}', 
                                f'{formSetLabel} Time: {canvas.formSetTime.get()}', f'Reset Voltage: {canvas.resetVoltage.get()}',
                                f'End Reset Voltage: {canvas.minResetVoltage.get()}',
                                f'Read1 Voltage: {canvas.formSetReadVoltage.get()}', f'Read1 Time: {canvas.formSetReadTime.get()}',
                                f'Read2 Voltage: {canvas.resetReadVoltage.get()}', f'Read2 Time: {canvas.resetReadTime.get()}',
                                f'Delay Time: {canvas.delayPeriodTime.get()}', f'Number of Cycles: {canvas.cycleNumber.get()}', 
                                f'Steps per Direction: {canvas.stepNumber.get()}', f'Range Test: {canvas.utilizeCurResRange.get()}']
            else: # if not hard coding and are doing LRS, rangeGateVoltage is needed
                info_lines = [f'ReRAM 64x64 GUI Test: {testName}', f'Gate Voltage: {canvas.gateVoltage.get()}', 
                                f'End Gate Voltage: {canvas.minGateVoltage.get()}',
                                f'{formSetLabel} Mode: {formSetLabel}' ,f'{formSetLabel} Voltage: {canvas.formSetVoltage.get()}', 
                                f'{formSetLabel} Time: {canvas.formSetTime.get()}', f'Reset Voltage: {canvas.resetVoltage.get()}',
                                f'Read1 Voltage: {canvas.formSetReadVoltage.get()}', f'Read1 Time: {canvas.formSetReadTime.get()}',
                                f'Read2 Voltage: {canvas.resetReadVoltage.get()}', f'Read2 Time: {canvas.resetReadTime.get()}',
                                f'Delay Time: {canvas.delayPeriodTime.get()}', f'Number of Cycles: {canvas.cycleNumber.get()}', 
                                f'Steps per Direction: {canvas.stepNumber.get()}', f'Range Test: {canvas.utilizeCurResRange.get()}']
        
        else:
            
            info_lines = [f'ReRAM 64x64 GUI Test: {testName}', f'Gate Voltage: {canvas.gateVoltage.get()}', 
                            f'{formSetLabel} Mode: {formSetLabel}' ,f'{formSetLabel} Voltage: {canvas.formSetVoltage.get()}', 
                            f'{formSetLabel} Time: {canvas.formSetTime.get()}', f'Reset Voltage: {canvas.resetVoltage.get()}',
                            f'Read1 Voltage: {canvas.formSetReadVoltage.get()}', f'Read1 Time: {canvas.formSetReadTime.get()}',
                            f'Read2 Voltage: {canvas.resetReadVoltage.get()}', f'Read2 Time: {canvas.resetReadTime.get()}',
                            f'Delay Time: {canvas.delayPeriodTime.get()}', f'Number of Cycles: {canvas.cycleNumber.get()}', 
                            f'Steps per Direction: {canvas.stepNumber.get()}', f'Range Test: {canvas.utilizeCurResRange.get()}']
        
        return info_lines
