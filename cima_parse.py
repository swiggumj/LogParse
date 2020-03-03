#!/usr/bin/env python
from __future__ import print_function

from datetime import datetime

#def get_cmd(line,cmd0='{',cmd1='}'):
#    return line[line.find(cmd0)+len(cmd0):line.rfind(cmd1)]

def measure_duration_sec(t0_str,t1_str,fmt='%Y-%b-%d %X'):
    T0 = datetime.strptime(t0_str, fmt)
    T1 = datetime.strptime(t1_str, fmt)
    return (T1-T0).seconds

def find_line_with_string(lines,test_str):
    for i,l in enumerate(lines):
        if test_str in l:
            return i
        else:
            continue
    return 99999999 

class cimalog():
    
    def __init__(self,cima_file):

        if '/' in cima_file:
            self.PATH = '/'.join(cima_file.split('/')[:-1])
            self.FILE = cima_file.split('/')[-1]
            self.FILEPATH = cima_file
        else:
            self.PATH = '.'
            self.FILE = cima_file
            self.FILEPATH = cima_file
        
        cimafile = open(self.FILEPATH,'r')
        self.lines = cimafile.readlines()
        cimafile.close()
        self.PROJECT = self.FILE.split('.')[0]
        #print(self.PROJECT)        

        # Get .cmd file name
        cmd_file_line = self.lines[find_line_with_string(self.lines,'CIMA-load_command_file: Loaded command file')]
        self.CMD_FILE = cmd_file_line.split()[-1].replace("'","")
        #print(self.CMD_FILE)

        # Read .cmd file, get line #s (ignore blank lines/comments)
        cmdfile = open(self.PATH+'/'+self.CMD_FILE,'r')
        self.cmds = cmdfile.readlines()
        self.search_cmd = []
        for i,c in enumerate(self.cmds):
            if c[0] == '#':    # Ignore comments.
                continue
            elif len(c) <= 2:    # Ignore new/blank lines.
                continue
            else:
                self.search_cmd.append('COMMAND run_command_line: EXECUTING command %s:' % (i+1))
                # Add to gather scan #s
                # ?? self.search_cmd.append('Coherent mode Started  with Scan number')
                #print('%s: %s' % (i,c))

        #print(len(self.search_cmd))
        self.CIMALINES = []
        start_line_ind = find_line_with_string(self.lines,"executive: CIMA executive ready")
        end_line_ind = find_line_with_string(self.lines,"CIMA-exit_cima: Exiting CIMA ...")
        #print(end_line_ind)

        #print(self.lines[start_line_ind],self.lines[end_line_ind])

        # AT SOME POINT: function to sort CIMALINES by timestamps...
        # Gather important info: start/end/search_cmd/etc. 
        self.CIMALINES.append(cimaline(self.lines[start_line_ind]))
        #print(len(self.search_cmd))
        for i,sc in enumerate(self.search_cmd):
            l_return = find_line_with_string(self.lines,sc)
            #print(i,l_return,sc)
            #print('\n%s\n%s\n' % (sc,self.lines[l_return]))
            try:
                self.CIMALINES.append(cimaline(self.lines[l_return]))
            # search_cmd assembled from cmd file, so index error if cmds are never reached (i.e. obs aborted)
            except IndexError:
                #print('Something is going wrong...')
                pass 
        self.CIMALINES.append(cimaline(self.lines[end_line_ind]))

        self.START = self.CIMALINES[0].timestamp
        self.END = self.CIMALINES[-1].timestamp
        self.obs_duration_sec = measure_duration_sec(self.START,self.END)

        SCAN_NUMBER = 0
        ss = None
        self.scans = []
        # EACH NEW SOURCE/FREQ BLOCK STARTS WITH A "LOAD" (obs. freq.)
        # Find these, then source blocks are 8 lines each...?
        for i,cl in enumerate(self.CIMALINES):
            if 'LOAD' in cl.description:
                if SCAN_NUMBER > 0:
                    # Check complete before appending?
                    self.scans.append(ss)
                ss = scan(SCAN_NUMBER,cl.timestamp)
                ss.tLOAD = measure_duration_sec(cl.timestamp,self.CIMALINES[i+1].timestamp)
                ss.freq = cl.description.split('.')[0].split('_')[-1]
                SCAN_NUMBER += 1
            elif 'SEEK' in cl.description:
                ss.tSEEK = measure_duration_sec(cl.timestamp,self.CIMALINES[i+1].timestamp)
                ss.psr = cl.description.split()[-1].replace("'","")
            elif 'ADJUSTPOWER' in cl.description: 
                ss.tPOWER = measure_duration_sec(cl.timestamp,self.CIMALINES[i+1].timestamp)
            elif 'SETUP pulsaron' in cl.description:
                for elem in cl.description.split():
                    if 'secs' in elem:
                        if elem.split('=')[0] == 'calsecs':
                            ss.tCAL = elem.split('=')[1]
                        elif elem.split('=')[0] == 'secs': 
                            ss.tPSRcmd = elem.split('=')[1]
            elif 'PULSARON' in cl.description:
                ss.tOBS = measure_duration_sec(cl.timestamp,self.CIMALINES[i+1].timestamp) 
                ss.tPSR = int(ss.tOBS)-int(ss.tCAL)
                ss.end_dt = self.CIMALINES[i+1].timestamp


        # Add final scan to array and check complete, etc. 
        self.scans.append(ss)
        self.sources = self.source_list()
        self.summary()

    def source_list(self):
        psrs = []
        for ss in self.scans:
            if ss.psr not in psrs:
                psrs.append(ss.psr)
        return psrs

    def summary(self):
        
        # Operator name
        # How many sources?
        # What frequencies? Etc. 
        print('')
        print('### NANOGrav %s observation (%.1f hours; %s sources)' % 
            (self.PROJECT,self.obs_duration_sec/3600.0,len(self.sources)))
        print('### %s - %s' % (self.START,self.END))
        #print('### %s sources: %s' % (len(self.sources),", ".join(self.sources)))
        print('### %s' % (self.CMD_FILE.replace("'","")))
        print('')
        for ss in self.scans:
            outstr = ('--%s sec--> %s @ %s MHz: %s sec on-source (%s sec requested)' %
                (str(ss.tSEEK).rjust(3).replace(' ','-'),ss.psr.ljust(10),
                ss.freq.ljust(4),ss.tPSR,ss.tPSRcmd))
            if ss.attribute_exists(ss.tPSR) and ss.attribute_exists(ss.tPSRcmd):
                if int(ss.tPSR) < int(ss.tPSRcmd): outstr+=' ***'
            if not ss.check_complete(): outstr+=' INC'
            print(outstr)

class cimaline():

    def __init__(self,cima_str):

        self.line = cima_str
        self.timestamp = self.line[0:20].strip()
        self.type = self.line[21:28].strip()
        self.description = self.line[28:].strip()
       
class scan():

    # Get requested duration of pulsar/cal scans
    # Measure duration of PULSARON

    def __init__(self,scan_number,start_dt):
        self.num = scan_number
        self.par = None  # Eventually...
        self.psr = None
        self.freq = None
        self.start_dt = start_dt
        self.end_dt = None

        self.tLOAD = None
        self.tSEEK = None
        self.tPOWER = None
        self.tOBS = None
        self.tCAL = None 
        self.tPSR = None 
        self.tPSRcmd = None  # _Requested_ on-source time; parse from SETUP line.

    def attribute_exists(self,attr):
        if attr is not None:
            return 1
        else:
            return 0

    # Check more things?
    def check_complete(self):

        test = 1
        test *= self.attribute_exists(self.freq)
        test *= self.attribute_exists(self.psr)
        test *= self.attribute_exists(self.tOBS)
        test *= self.attribute_exists(self.tLOAD)
        test *= self.attribute_exists(self.tSEEK)
        test *= self.attribute_exists(self.tPOWER)
        return test

    # Should assemble other checks/warnings...
    def assemble_warnings(self):
        pass


# MAIN
logfile = open('new-logs.txt','r')
new_logs = logfile.readlines()
logfile.close()

nlogs = len(new_logs)
if nlogs > 0:
    for nl in new_logs:
        x = cimalog(nl.strip())
else:
    print('No new observations in the past 24 hrs.')
