#--------------------------------------------------------------------------------------------------------------
#
#  treckr.py
#
#  Version: 0.5
#
#  Copyright (C) 2019 Eckhard Delfs
#
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#
#  Apple II is a trademark of Apple Inc.
#
#  Version history: 
#  - 0.5: May 30, 2019  - Restructuring; added function to parse .raw files ('r')  
#  - 0.1: March   2019  - First version
#
#--------------------------------------------------------------------------------------------------------------
import serial, time, binascii, os, errno, sys
#--------------------------------------------------------------------------------------------------------------
#
# Definition of USB serial port connected to board
#
# <<<<<<< CHANGE HERE FOR YOUR SETTINGS >>>>>>>>>>
#
SERIAL_PORT = "COM6"  
#
# ------------------------------------------------------------------------------------------------------------- 

# global definitions, don't change
# -------------------------------------------------------------------------------------------------------------
RAW_TRACK_SIZE = (7*1024)              # memory used by Arduino to capture the raw contents of one track [in bytes]
SECTOR_SIZE    = 256                   # net storage capacity of one DOS sector
MAX_SECTORS    = 16                    # number of sectors per disk track
TRACK_SIZE     = (MAX_SECTORS * SECTOR_SIZE) # Net storage capacity of one track (16 sectors with 256 bytes each)
MAX_TRACKS     = 40                    # maximum number of tracks in DOS3.3 format (160KB)
DEF_TRACKS     = 35                    # default number of tracks in DOS3.3 format (140KB)
DEF_ROUND      = 32                    # default rounding value used by Arduino when calculating time delta between 2 events
DIR_TRACK      = 17                    # track number hosting the VTOC and table of contents
RETRY_ATTEMPTS = 3                     # max number of retry attempts when positioning the track motor 
BAUD_RATE      = 500000                # Baud rate used on serial connection
DISK_DIR_NAME  = "disks"               # name directory path containing the DOS 3.3 image disk files
VERSION        = "Version 0.5"         # Treckr Version
QSCAN_TRACKS   = [0,1,2,3,4,DIR_TRACK] # list of tracks to be scanned in quick mode
DEBUG          = False                 # control print of debug messages
# -------------------------------------------------------------------------------------------------------------


class SerialConnection:
    def __init__(self):
        self.configured = False # default start condition of serial connection to board; not initialized
        self.target     = None
        
    def setup( self):
        """ sets up serial connection to Arduino board (target) """
        try:
            if not self.configured:
                sys.stdout.write( "Setting up serial port " + SERIAL_PORT + " ....")
                sys.stdout.flush()
                self.target = serial.Serial( SERIAL_PORT, BAUD_RATE, timeout=0.2)
                time.sleep(1) #give the connection a second to settle 	
                self.configured = True     
                print("ok.") 
        except Exception as e:
            print("failed. Board not connected? Wrong port?")
            print(str(e))
            return False
        return True  
        
    def is_established( self):
        """ returns logical state of serial connection to Arduino board (target) """
        if not self.configured:
            return False
        return True    
        
    def shutdown( self):
        """ resets serial connection to Arduino board (target) """
        if self.configured:
            self.target.close()
            self.configured = False     
        return      
      
    def enter_single_track_mode( self):
        """ triggers target for single track read mode """
        if not self.configured:
            print("Error: enter_single_track_mode(): serial IF not configured.")
            return None
        else: 
            self.target.write( bytearray("r", "utf-8"))
        return
        
    def enter_main_loop( self):
        """ configure target to leave single track read mode and enter main loop """
        if not self.configured:
            print("Error: enter_main_loop(): serial IF not configured.")
            return
        else: 
            self.target.write( bytearray(b'.\xf0'))
            # wait for target response
            while self.target.in_waiting<1:
                continue
            response = self.target.read(1)    
        return
               
    def read_track_from_drive( self, track_id, delay):
        """ read disk track <track_id> with round value <delay> from drive """
        if not self.configured:
            print("Error: read_track_from_drive(): serial IF not configured.")
            return None
        else:
            command = bytearray(3)	
            response = bytearray(1)
   
            command[0] = 0x80        # READ command
            command[1] = track_id    # track to be read
            command[2] = delay       #  delay used by target time stamp calculation
        
            if( 3 == self.target.write( command)):  
                while self.target.in_waiting<1:
                    continue
            response = self.target.read(1) 	
            if( response[0] == 0x40):
                while self.target.in_waiting < RAW_TRACK_SIZE:
                    continue
                return self.target.read( RAW_TRACK_SIZE)
            debug("Debug: read_track_from_drive: unexpected response code: " + str( response))
            return None

    def reset_track_motor( self, track_no):
        """ forces track motor to reset and return to requested position <track_no> """
        command = bytearray(3)	
        response = bytearray(1) 
        
        command[0] = 0x80 #READ
        command[1] = track_no
        command[2] = 255
        if( 3 == self.target.write(command)): 
            while self.target.in_waiting<1:
                continue
            response = self.target.read(1) 	 # don't check response
        return

    def run_self_test( self):
        """ runs Arduino self test """
        # configure target for serial test mode
        self.target.write( bytearray( "t", "utf-8"))  
  
        # send test serial command
        self.target.write( bytearray( b'\xa0'))     
      
        while self.target.in_waiting<1:
            continue
        response = self.target.read(1)  
        while self.target.in_waiting < RAW_TRACK_SIZE:
            continue
        result = self.target.read( RAW_TRACK_SIZE)
      
        # send test serial command
        self.target.write( bytearray(b'\xf0'))
        while self.target.in_waiting<1:
            continue
        response = self.target.read(1)  
        if( ord(response) == 0x60):
            return True
        return False    
 
def debug( message):
    if DEBUG:
        print( message)
    return		
 
#--------------------------------------------------------------------------------------------------------------
#
# read track from drive and convert to DOS 3.3 format
# 
# input:
#         target:   serial IF to board
#         track_no: number of requested track to be read (0..39)
#         repeat_counter:  how many times shall be attempted to reposition the track motor in case of errors
#                          if set to 0, also limit the number of read attempts per track to 3
# returns:
#         rc:               True (ok); False (track could not be read)
#         read_sectors:     number of decoded sectors in this track
#         list:             list of missing logical sectors
#         track_dec:        16*256 bytes of decoded data fields 
#
# ------------------------------------------------------------------------------------------------------------- 
def track_read( connection, track_no, repos_attempts):
	  
    track_dec_phys_total = {}
    missing_logical_sector_list=[]
    track_dec=bytearray()   
    total_track_dec=[]  
    round_success_list=[]
    # round values to be used by assembly read function on board for each retry
    ROUND_VALUES =[32, 32, 32, 32, 34, 34, 36, 36, 38, 38, 30, 30, 28, 28, 26, 26] # length needs to be power of 2
    
    attempts = 0
    if repos_attempts == 0:
        max_attempts = 8 # fast mode for quick scan
    else:
        max_attempts = len( ROUND_VALUES) * repos_attempts
        
    finished=False
    while not finished:
        # read requested track from drive
        track = connection.read_track_from_drive( track_no, ROUND_VALUES[attempts % len(ROUND_VALUES)])
        attempts+=1
        if track == None:
            print("track==None")
            break    
        # decode track and get content of physical sectors
        # note that the sector list may be incomplete
        read_track_no, track_dec_phys = track_decode_dos33( track.hex())
        if( track_no == read_track_no):
            # search for new sectors in this read attempts
            # if available, add them to dictionary track_dec_phys_total
            for sector in track_dec_phys:
                if sector not in track_dec_phys_total:
                    track_dec_phys_total[sector] = track_dec_phys[sector]
                    print("Track: ", track_no,". Decoded Sectors:", len( track_dec_phys_total), end="\r", flush=True)
                    # log ROUND_VALUE (debug purposes)
                    round_success_list.append( ROUND_VALUES[attempts % len(ROUND_VALUES)])
                    					
        # check if all sectors in current track have been decoded successfully         
        if( len( track_dec_phys_total) == MAX_SECTORS) or (attempts == max_attempts):
            finished=True
        # reposition track motor if all attempts failed        
        elif( attempts % len( ROUND_VALUES) == 0):
            connection.reset_track_motor( track_no)
	
    sectors_read = len(	track_dec_phys_total)
    j=0
    while j<MAX_SECTORS:
        # fill missing physical sectors with all zero pattern
        if j not in track_dec_phys_total:
            track_dec_phys_total[j] = [0 for i in range( SECTOR_SIZE)]
            missing_logical_sector_list.append(j)
        j+=1
                
    # now reassemble 16 physical to 16 logical sectors
   	# e.g. logical sector 13 maps to physical sector 1
    physical_2_logical_sector_mapping_list=[0,13,11,9,7,5,3,1,14,12,10,8,6,4,2,15]
    for j in physical_2_logical_sector_mapping_list:
        track_dec += bytes( track_dec_phys_total[j])			
          	  
    if( sectors_read == MAX_SECTORS):
        print("Track ", track_no, ": ", MAX_SECTORS," sectors decoded correctly.       ", sep='')
    else:
        print("Track ", track_no, ". Incomplete track read. Sector(s) ", str( sorted( missing_logical_sector_list)), " could not be decoded.", sep='')

   # print(read_sectors, missing_logical_sector_list)
    return True, len( track_dec_phys_total), sorted( missing_logical_sector_list), round_success_list, track_dec
	

#--------------------------------------------------------------------------------------------------------------
#
# decode DOS 3.3 sector address field
#
# -------------------------------------------------------------------------------------------------------------     
def check_address_field( header):
    # check if the header field trailer is at the expected position; check only the first two bytes (0xde, 0xaa)
    
    if( header[-1] != 0xaa or header[-2] != 0xde):
        return False, 0, 0 # trailer of sector address header corrupt
        
    volume_no = ((header[3] << 1) | (header[3] >> 7)) & header[4]
    track_no  = ((header[5] << 1) | (header[5] >> 7)) & header[6]
    sector_no = ((header[7] << 1) | (header[7] >> 7)) & header[8]
    sum_no    = ((header[9] << 1) | (header[9] >> 7)) & header[10]
        
    if( sum_no != (volume_no ^ track_no ^ sector_no)):
        return False, 0, 0 # error in sector address header checksum
        
    if( track_no > MAX_TRACKS) or (sector_no > MAX_SECTORS):
        return False, 0, 0 
    return True, track_no, sector_no # sector address header ok


#--------------------------------------------------------------------------------------------------------------
#
# decode DOS 3.3 sector data field
#
# ------------------------------------------------------------------------------------------------------------- 

# LUT = look up table for decoding 6-bit data words
LUT =     [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
           0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x02, 0x03, 0x00, 0x04, 0x05, 0x06,
           0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x08, 0x00, 0x00, 0x00, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
           0x00, 0x00, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x00, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a,
           0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1b, 0x00, 0x1c, 0x1d, 0x1e,
           0x00, 0x00, 0x00, 0x1f, 0x00, 0x00, 0x20, 0x21, 0x00, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,                                 
           0x00, 0x00, 0x00, 0x00, 0x00, 0x29, 0x2a, 0x2b, 0x00, 0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x32,
           0x00, 0x00, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x00, 0x39, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f] 

def decode_data_field( data_field):
  
    data_256=[]
    # check if data field has correct trailer
    if( data_field[-1] != 0xeb or data_field[-2] != 0xaa or data_field[-3] != 0xde):
        return False, data_256

    # DOS 3.3 data fields consists of five parts
    # 3 byte header: d5-aa-ad
    # 256 bytes field containing encoded representation of lower 6-bits (torso) of the unencoded data field
    # 86 bytes field containing encoded representation of multiplexed higher 2-bits of unencoded data field;
    #          the unencoded 256 field is structured in 3 columns, where the 2-bit values of three columns are grouped in one code word
    #          the decoding of a 6bit->8bit value is done using a look up table (LUT)
    # 1 byte checksum
    # 3 byte trailer: 0xde-0xaa-0xeb
  
    # step 1 - decode first 86 bytes of encoded block in 6-bit values
    dec=0
    data_256_2_8=[]
    i=0
    while i<86:
        dec ^= LUT[data_field[i] & 0x7f]
        data_256_2_8.insert( 0, dec)
        i+=1  
  
    # step 2 - decode remaining 256 bytes of encoded block in 6-bit values
    while i<342:
        dec ^= LUT[data_field[i] & 0x7f]
        data_256.append( dec << 2)
        i+=1  

    # step 3 - verify checksum (XOR of data bytes)
    if (dec != LUT[data_field[342] & 0x7f]): 
        #print("CRC error")
        return False, data_256
    
   # print([hex(x) for x in data_256])
    #print([hex(x) for x in data_256_2_8])
    
    # step 4 - demux the 86 bytes containing 3 muxed pairs of 2 MSBs and insert them as MSBs next to the 6-bit torso fields of the remaining 256 byte field
    # processing is done in three columns: 84 bytes, 86 bytes, 86 bytes: first group is smaller because two 2-bit fields are unused (86*6=512+2*2)
    i=0
    while i<84: 
        p = ((data_256_2_8[2+i]>>4) & 3)
        if(p==2): p=1
        elif (p==1): p=2
        data_256[255-i] |= p
        i+=1
  
    i=0  
    while i<86:
        p = ((data_256_2_8[i]>>2) & 3)
        if(p==2): p=1
        elif(p==1): p=2
        data_256[171-i] |= p
        i+=1
  
    i=0  
    while i<86:
        p = ((data_256_2_8[i]) & 3)
        if(p==2): p=1
        elif(p==1): p=2
        data_256[85-i] |= p
        i+=1
   
    return True, data_256


#--------------------------------------------------------------------------------------------------------------
#
# decode track into DOS 3.3 sector format
# 
# input:
#         track: data retrieved from board (string with length of 7KB)
# returns:
#         track_no: number of track
#         sector_list: list of successfully decoded sectors (sector header + data field)
#         track_dec: list of decoded data sectors (16*256 bytes). An invalid data field is replaced by an empty field (all 256 bytes set to 0)
#   
# -------------------------------------------------------------------------------------------------------------   
def track_decode_dos33( track):
    
    track_dec_phys={}
    track_no = 255 # initialize with invalid number
    
    adr_field_header  = "d5aa96"
    adr_field_size    = 13*2 # 13 bytes
    data_field_header = "d5aaad"
    data_field_size   = 349*2 # 349 bytes
    
    finished=False
    while not finished:
        # search for next address field header
        s=track.find( adr_field_header)
        if s == -1:
            finished=True
            break
        # sector field header has been found
        # check if remaining size of the track is smaller than a sector field (26 nibbles)
        if len( track[s:]) < adr_field_size:
            finished=True
            break
        try:    
        # convert address field into list of 8bit integers
            address_field = [int(track[s+i:s+i+2],16) for i in range( 0, adr_field_size, 2)]
        except:
            print(track[s:s+adr_field_size])
            exit(1)
        # check sector field header field content
        adr_field_ok, track_no, sector_no = check_address_field( address_field)
        if not adr_field_ok:
            # sector field is invalid
            #print("Header error")
            track=track[s+adr_field_size:]
            break         
          
        # address field is valid; advance by length of address field header 
        track=track[s+adr_field_size:]
        # now search for data field header
        t=track.find( data_field_header)
        if( t == -1):
            # no data field found
            finished=True
            break   
              
        # check if remaining track length is sufficient to contain a complete data field
        if( len(track[t+6:]) < data_field_size):
            finished=True
            break
        # check that data field belongs to the current sector 
        if( t > 50*2):
            break # data field header too far away from address field header ; ignore this sector
            
        data_field = [int(track[t+i:t+i+2],16) for i in range( 6, data_field_size, 2)]
        # decode data field
        data_field_ok, data_dec = decode_data_field( data_field)
        
        if data_field_ok:
            if sector_no not in track_dec_phys:
                # data field is ok; insert sector in result list
                track_dec_phys[sector_no] = data_dec
            if len( track_dec_phys) == MAX_SECTORS:
                finished=True
                break
              
    return track_no, track_dec_phys
  
#--------------------------------------------------------------------------------------------------------------
#
# decode DIR_TRACK containing VTOC and list DOS3.3 directory (if table of contents is located in track 17)
#
# input:
#         sector_list:  list of missing sectors in this track
#         disk_dec:     16x256 bytes data field in this track
#         mode:         False: only print VTOC info
#                       True:  print VTOC and directory of files in DOS 3.3 format
# returns:
#         disk_no_tracks: number of tracks in this disk
#         disk_no_sectors: number of sectors in this disk
#         disk_os_version: DOS version of this disk 
# ------------------------------------------------------------------------------------------------------------- 
def analyze_dir_track( sector_list, disk_dec, print_full_directory):
	
	# sector 0 contains VTOC info; check if present
    if(0 not in sector_list):
  	    # assemble VTOC info from sector 0
        disk_os_version=disk_dec[3]
        disk_volume=disk_dec[6]
        disk_no_tracks=disk_dec[0x34]
        disk_no_sectors=disk_dec[0x35]
        print("VTOC Info: Dos 3.", disk_os_version, ", Volume: ", disk_volume, ", Tracks: ", disk_no_tracks, ", Sectors: ", disk_no_sectors, sep='') 
 
        if print_full_directory:
            catalog_track = disk_dec[1]
            if( catalog_track == DIR_TRACK):
                # read catalog    
                directory = read_catalog( disk_dec)       
                for i in directory:
                    print("{0} {1:03} {2}".format(i[1],i[2],i[0]))  
            else:
                print("Catalog Sector not in Track ",DIR_TRACK, "! Track is: ", catalog_track)  
    else:
        print("VTOC info not present.")
        disk_no_tracks=MAX_TRACKS
        disk_no_sectors=MAX_SECTORS
        disk_os_version=0
    return disk_no_tracks, disk_no_sectors, disk_os_version    
	

#--------------------------------------------------------------------------------------------------------------
#
# read catalog info and returns result in list
#
# input:
#         disk_dec   :  byte array containing track 17 (track with table of contents)
#  
# returns:
#         directory: list of directory entries
#                    file name (30 characters)
#                    file type ( 3 characters)
#                    file length
#                    track offset of first sector list sector
#                    sector offset of first sector list secto
#   
# ------------------------------------------------------------------------------------------------------------- 
def read_catalog( disk_dec):
	
    def decode_catalog_sector( sector, directory):
        """ decode DOS 3.3 disk catalog sector """
    
        file_type_table={0x00:"  T", 0x80:" *T", 0x01:"  I", 0x81:" *I", 0x02:"  A", 0x82:" *A", 0x04:"  B", 0x84:" *B", \
                         0x08:"  S", 0x88:" *S", 0x10:"  R", 0x90:" *R", 0x20:" AT", 0xA0:"*AT", 0x40:" BT", 0xC0:"*BT"}   
    
        # check some default pattern in catalog sector; all following bytes should be zero
        zero_byte_offsets = [0,3,4,5,6,7,8,9,10]
        for i in zero_byte_offsets:
            if sector[i] != 0:
                debug("decode_catalog_sector: catalog sector badly formatted")
                return False
        
        # following list contains byte offsets of 7 file entries in catalog sector        
        file_entry_offsets = [11,46,81,116,151,186,221]
        for i in file_entry_offsets:
            #check if entry is final one or contains deleted entry. If so, skip entry
            if (sector[i] == 0) or (sector[i] == 0xFF):
                continue
            # check if entry points to invalid track/sector list. If so, skip entry
            if( sector[i] >= MAX_TRACKS) or (sector[i+1] >= MAX_SECTORS):
                continue
            # extract file type
            if sector[i+2] in file_type_table:
                file_type=file_type_table[sector[i+2]]   
            else:
                file_type="UDF"     
            file_name=sector[i+3:i+33]
            file_length=sector[i+33]  
            # file name needs to be converted in ASCII    
            file_name = bytearray( i&0x7f for i in file_name)   
            try:    
                directory.append([file_name.decode("ascii"), str( file_type), file_length, sector[i], sector[i+1]])
            except UnicodeDecodeError:
                directory.append(["FILE NAME COULD NOT BE DECODED", str( file_type), file_length, sector[i], sector[i+1]])   
        return True       
   
    # implementation starts here
    directory = []
    offset = disk_dec[2] * SECTOR_SIZE # VTOC offset to first catalog sector (usually last sector on track 17)
	
    finished=False
    while not finished:
        sector = disk_dec[offset:offset + SECTOR_SIZE]
        if( len( sector) == SECTOR_SIZE):
            if (sector[1] > MAX_TRACKS-1 or sector[2] > MAX_SECTORS-1):
                print("Invalid catalog information. Track:", catalog_track, " Sector:", catalog_sector,".", sep='')
                finished = True    
            elif ( sector[1] == 0) and (sector[2] == 0):
                # last catalog sector found
                finished = True   
            else:      
                # decode next catalog sector
                if not decode_catalog_sector( sector, directory):
                    debug( "debug decode_catalog_sector(): error in catalog sector decoding")
                    finished = True
                offset = sector[2] * SECTOR_SIZE    
        else:
            # invalid VTOC data
            finished=True		
    return directory
 
#--------------------------------------------------------------------------------------------------------------
#
# read sector usage list
#
# Using the table of contents, function assembles the track/sector lists for each file and stores them in a list.
#
# input:
#             disk_dec  :  byte array containing entire disk
#             directory :  list containing disk table of contents
#     
# returns:
#      total_sector_list:  list of track/sector lists for each file in the directory
#                
# ------------------------------------------------------------------------------------------------------------- 	
def read_sector_list( disk_dec, directory):

    total_sector_list = []
    for i in directory:
        sector_list   = []
        file_length   = i[2] 
        track_offset  = i[3]
        sector_offset = i[4]
        
        if(( track_offset > MAX_TRACKS-1) or (sector_offset > MAX_SECTORS-1) or (file_length == 0)): # check if entries are valid
            finished=True
        else:
            sector_list.append([track_offset, sector_offset]) # initialize sector list with first entry
            finished=False
            file_length-=1  # remove first T/S list entry
            if( file_length == 0): # rare case in DOS3.3 
                finished=True
            
        while not finished:
            offset = (TRACK_SIZE * track_offset) + (SECTOR_SIZE * sector_offset)
            _list  = disk_dec[offset:offset + SECTOR_SIZE]
            if( len(_list) == SECTOR_SIZE):
                 if(( _list[0] | _list[3] | _list[4]) == 0): # check if a few default entries are zero
                    # a list sector contains 122 T/S pair entries max.
                    gen_list = (x for x in range (0, min( 244, file_length*2), 2))
                    for x in gen_list:
                        sector_list.append([_list[12+x], _list[12+x+1]]) # 12 is offset for first pair of track/sector entries
                    file_length -= 123 # reduce length by max value for T/S sector
                    if file_length <= 2: # extended list requires at least one more T/S sector + data sector
                        finished = True
                    else:
                        track_offset  = _list[1]
                        sector_offset = _list[2]
                        file_length-=1 # reduce by second T/S entry               
                        if( track_offset == 0): # last sector list sector belonging to this file?
                            sector_list.append(["INVALID CONT.", "INVALID CONT."])  
                            finished=True                  
                        else:
                            sector_list.append([track_offset, sector_offset]) # update sector list with second T/S list
                 else:
                    sector_list.append(["INVALID", "INVALID"])  
                    # list seems corrupted
                    finished=True 
            else:
                sector_list.append(["INVALID", "INVALID"])  
                finished=True
           # print(sector_list)
        total_sector_list.append( sector_list)
  
    return total_sector_list
  
       
#--------------------------------------------------------------------------------------------------------------
#
# Test serial connection to board
#
# -------------------------------------------------------------------------------------------------------------
def test_serial( connection):      
    # setup serial connection if necessary
    if not connection.is_established():
        if not connection.setup():
            print("Test failed")
            return
                  
    # now trigger self test
    if connection.is_established():
        print("Testing serial connection to target ....", end = '')
        if connection.run_self_test():
            print("ok.")   
        else:
            print("failed.  --> please try again.")
            connection.shutdown()
    return  

  
#--------------------------------------------------------------------------------------------------------------
#
# Read DOS 3.3 directory from track 17
#
# Input: mode (True/False) 
#        False: read track DIR_TRACK, but do not show directory
#        True:  read track DIR_TRACK and show directory
#
# ------------------------------------------------------------------------------------------------------------- 
def _read_disk_directory( connection):
    read_disk_directory( connection, True)
    return

def read_disk_directory( connection, mode): 
    # setup serial connection if necessary
    if not connection.is_established():
        if not connection.setup():
            print("Cannot connect to drive.")
            return
    
    # configure target for single track read mode
    connection.enter_single_track_mode()
          
    # read Track 17 containing VTOC and catalog sectors
    result, read_sectors, missing_sector_list, round_list, disk_dec = track_read( connection, DIR_TRACK, 1)
    # configure target to leave single track read mode and enter main loop
    connection.enter_main_loop()      
             
    if( result == True):
        disk_no_tracks, disk_no_sectors, disk_version = analyze_dir_track( missing_sector_list, disk_dec, mode)   
        return True, disk_no_tracks, disk_no_sectors, disk_version
    else:
        return False, 0, 0, 0

 
#--------------------------------------------------------------------------------------------------------------
#
# Capture raw disk to host file
#
# ------------------------------------------------------------------------------------------------------------- 
def capture_raw_disk_to_host_file( connection):
    if not connection.is_established():
        if not connection.setup():
            return
      
    user_input = input( "Insert disk. Enter a filename for the disk (.raw is appended automatically): ")
    try:
        os.mkdir( DISK_DIR_NAME, 0o700)
    except OSError as e:
        if(e.errno != errno.EEXIST):
            print("Cannot create directory", DISK_DIR_NAME, "in current directory")
            exit()

    disk_name = DISK_DIR_NAME + "/" + user_input + ".raw"
    if not os.path.isfile( disk_name):
        # configure target for single track read mode
        connection.enter_single_track_mode()
        try:
            with open(disk_name, "wb") as file:
                i=0 
                while i<MAX_TRACKS:
      	            # read track i with default delay (best effort mode, as track format is unknown)
                    track_data = connection.read_track_from_drive( i, DEF_ROUND)
                    print("Storing track:", i, "to file.")
                    file.write( track_data)               
                    i+=1 # move to next track              
                file.close()   
        except Exception as e:
            print("Error during generation of", disk_name,".")   
            print(str(e))
        
        # configure target to leave single track read mode and enter main loop
        connection.enter_main_loop()           
    else:
        print("Error: File", disk_name, "already exists.")
    return
 
 
 
#--------------------------------------------------------------------------------------------------------------
#
# Converts .raw into .bin files and prints table of contents (experimental, for test reasons)
#
# ------------------------------------------------------------------------------------------------------------- 
def analyze_raw_disk_from_bin_file():
    
    user_input = input( "Enter input file name to be decoded (.raw is appended automatically): ")  
    disk_name = DISK_DIR_NAME + "/" + user_input + ".raw"
    disk_out_name = DISK_DIR_NAME + "/" + user_input + ".bin"
    
    # read input .raw file from file system
    try:
        with open( disk_name, "rb") as bin_file:
            disk_dec = bytearray( bin_file.read())
            bin_file.close()     
    except Exception as e:
        print("Error when trying to read", disk_name,".")   
        print( str(e))
        return
    
    print("\nDecoding", disk_name, "...\n")    
    track_dec=bytearray()  
    i=0
    while i<MAX_TRACKS: 
        read_sectors=0
        missing_logical_sector_list=[]
        # decode track to DOS3.3 format
        no, track_dec_phys = track_decode_dos33( disk_dec.hex()[(RAW_TRACK_SIZE*2)*i:(RAW_TRACK_SIZE*2)*i+RAW_TRACK_SIZE*2])
        track_dec_phys_total = {}
        for sector in track_dec_phys:
            if sector not in track_dec_phys_total:
                track_dec_phys_total[sector] = track_dec_phys[sector]
                read_sectors +=1
                
        # fill up missing physical sectors with all zero pattern      
        j=0
        while j<MAX_SECTORS:
          
            if j not in track_dec_phys_total:
                track_dec_phys_total[j] = [0 for i in range(SECTOR_SIZE)]
                missing_logical_sector_list.append(j)
                print("Track: ", i,". Decoded Sectors:", read_sectors, end="\r", flush=True)
            j+=1
                
        # now reassemble 16 physical to 16 logical sectors
        physical_2_logical_sector_mapping_list=[0,13,11,9,7,5,3,1,14,12,10,8,6,4,2,15]
        for j in physical_2_logical_sector_mapping_list:
            track_dec += bytes( track_dec_phys_total[j])    
        
        if( read_sectors == MAX_SECTORS):
            print("Track:", i, ".", MAX_SECTORS,"sectors decoded correctly.       ")
        else:
            print("Track:", i, ". Incomplete track read. Sector(s) ", str( sorted( missing_logical_sector_list)), " could not be decoded.", sep='')
            
        i+=1 # next track
        
    # write output to .bin file
    try:
        with open( disk_out_name, "wb") as bin_file:
            bin_file.write( track_dec) 
            print("\nOutput written to: ", disk_out_name,"\n")       
    
    except Exception as e:
        print("Error when trying to write ", disk_out_name,".")   
        print( str(e))
    
    # print VTOC and table of contents     
    track_offset = DIR_TRACK*TRACK_SIZE  
    analyze_dir_track([], track_dec[track_offset:track_offset+TRACK_SIZE], True)
    return
  
 

#--------------------------------------------------------------------------------------------------------------
#
# Runs quick scan of disk. Reads tracks 0-4, 17 and outputs DOS 3.3 sector analysis
#
# ------------------------------------------------------------------------------------------------------------- 
def quick_scan( connection):
    if not connection.is_established():
        if not connection.setup():
            print("Cannot connect to drive.")
            return

    print("Now running quick scan of disk. This will output the number of decoded DOS3.3 sectors in tracks", QSCAN_TRACKS,".")
    user_input = input( "Insert disk and press return: ")
 
    # configure target for single track read mode
    connection.enter_single_track_mode()

    # scan the tracks (last parameter '0' indicates fast mode, i.e. max 8 retry attempts)
    for i in QSCAN_TRACKS:
        result, read_sectors, missing_sector_list, round_list, disk_dec = track_read( connection, i, 0)      
    
    # configure target to leave single track read mode and enter main loop
    connection.enter_main_loop()     
    return
  
 
#--------------------------------------------------------------------------------------------------------------
#
# Capture DOS 3.3 disk to host file
#
# ------------------------------------------------------------------------------------------------------------- 
def capture_dos_disk_to_host_file( connection):
    
    if not connection.is_established():
        if not connection.setup():
            print("Cannot connect to drive.")
            return
              
    user_input = input( "Insert disk. Enter a filename for the disk (.bin and .txt are appended automatically): ")
     
    print("Now reading VTOC to check DOS version and number of available tracks on disk...")     
                 
    #read VTOC to check DOS version and number of available tracks on disk
    rc, disk_no_tracks, disk_no_sectors, disk_os_version = read_disk_directory( connection, False) # only read sector 0
    
    # check DOS version and number of tracks
    if( disk_os_version != 3):
        disk_no_tracks=DEF_TRACKS
        print("Invalid DOS version. Set number of tracks set to 35.")
  
    if( rc == True):
        try:
            os.mkdir( DISK_DIR_NAME, 0o700)
        except OSError as e:
            if(e.errno != errno.EEXIST):
                print("Cannot create directory", DISK_DIR_NAME, "in current directory")
                exit()
    
        disk_name = DISK_DIR_NAME + "/" + user_input + ".bin"
        disk_info = DISK_DIR_NAME + "/" + user_input + ".txt"
        
        #check if file already exists
        if not os.path.isfile( disk_name):
      	
            # configure target for single track read mode
                connection.enter_single_track_mode() # move !!!!
          
         #   try:
                with open( disk_name,"wb") as bin_file,\
                     open( disk_info,"w")  as txt_file:
                    i=0 
                    while i<disk_no_tracks:
                        info_text="Track: " + str(i) + ": "
                        result, read_sectors, missing_sector_list, round_list, disk_dec = track_read( connection, i, RETRY_ATTEMPTS)
                        if( read_sectors==MAX_SECTORS):
                            info_text += "ok. "
                        else:
                            info_text += "corrupt sectors: " + str( missing_sector_list) +". "
                        info_text += "List of round values: " + str( round_list) + ".\n"
                        bin_file.write( disk_dec)               
                        txt_file.write( info_text)
                        i+=1 # move to next track              
                bin_file.close()  
                txt_file.close() 
        #    except Exception as e:
       #        print("Error during generation of", disk_name, "or", disk_info, ".")
        #        print( str(e))
          
            # configure target to leave single track read mode and enter main loop
                connection.enter_main_loop()  # move back!!!!
        else:
            print("Error: File", disk_name, "or", disk_info, "already exists.")
    return
  

#--------------------------------------------------------------------------------------------------------------
#
# Write disk catalog data to two .info files:
#
# File:                  .bin file being processed
# txt_file:              File handle to summary file
# txt_file_short:        File handle to detailed information file
# disk_directory:        structure holding the disk table of contents
# sector_list:           structure holding the list of sectors used by files on disk
#
# ------------------------------------------------------------------------------------------------------------- 
def write_info_files( File, txt_file, txt_file_short, disk_directory, sector_list):
    # following loop serves to write the output in two flavors to the output files
    # info_ctr =0: short version with directory listing only goes into *.info 
    # info_ctr =1: full version with track/sector list goes into *_with_sector_list.info
    info_ctr = 0
    while( info_ctr < 2):
        if( info_ctr == 0):
            info_file = txt_file_short
        else:
            info_file = txt_file
               
        info_file.write("\n==================================================================================================\n")
        string = "FILE: " + File +"\n"
        info_file.write( string)
        info_file.write("==================================================================================================\n")
        # list disk directory in legacy format
        for i in disk_directory:
            info_file.write("{0} {1:03} {2}\n".format(i[1],i[2],i[0])) 
          
        if( info_ctr == 1):
            info_file.write("\nDetailed Track/Sector lists:\n")
            k=0
            for i in disk_directory:
                # print directory entry 
                info_file.write("--------------------------------------------------------------------------------------------------\n")
                info_file.write("{0} {1:03} {2}\n".format(i[1],i[2],i[0])) 
                info_file.write("--------------------------------------------------------------------------------------------------\n")
                j=0
                n=0
                # print list of sectors in columns of 10 entries
                while( j != len(sector_list[k])):
                    list_entry = "{0:8}".format(str(sector_list[k][j]))
                    info_file.write( list_entry)
                    if( j+1 != len(sector_list[k]) and (n != 9)):
                        info_file.write("  ")
                    n+=1
                    if( n==10):
                        info_file.write("\n")
                        n=0
                    j+=1
                k+=1
                info_file.write("\n") 
        info_ctr+=1 
    return               

#--------------------------------------------------------------------------------------------------------------
#
# Read DOS 3.3 binary file and produce catalog output in two .info files:
#
# .info:                  list of table of contents of all .bin files in the directory
# _with_sector_list.info: same as .info but with additional list of used sectors per file
#
# ------------------------------------------------------------------------------------------------------------- 
def generate_catalog_from_bin_file():
  
        print("Directory", DISK_DIR_NAME, "will be parsed for disk image files (*.bin). Enter disk.")
        user_input      = input("Enter output filename (file endings are added automatically): ")
        disk_info_short = DISK_DIR_NAME + "/" + user_input + ".info"
        disk_info       = DISK_DIR_NAME + "/" + user_input + "_with_sector_list.info"
  
   # try:
        with open( disk_info, "w") as txt_file, \
             open( disk_info_short, "w") as txt_file_short:
            host_directory = os.listdir( DISK_DIR_NAME)
      
            for File in host_directory:
                if(File.rfind( ".bin") != -1):
                    print("Processing:", File)
                    disk_directory = []
                    File_path = DISK_DIR_NAME + "/" + File
                    with open( File_path, "rb") as bin_file:
                        disk_dec = bytearray( bin_file.read())               
                        
                        # set track 17 as default track for directory search
                        track_offset = DIR_TRACK * TRACK_SIZE
                        if(( len( disk_dec) < track_offset) or (len( disk_dec) > MAX_TRACKS * TRACK_SIZE)):
                            message = "Error: File length <" + File + "> invalid (" + str( len( disk_dec)) + " bytes).\n"
                            debug(message)                    
                        else:
                            # generate disk table of contents
                            disk_directory = read_catalog( disk_dec[track_offset: track_offset+TRACK_SIZE])
                            # generate list of sectors used by the files
                            sector_list = read_sector_list (disk_dec, disk_directory)
                            # write info to files
                            write_info_files( File, txt_file, txt_file_short, disk_directory, sector_list)
                                         
   # except Exception as e:
   #     print( "Error during generation of", disk_info, ".")
   #     print( str( e))
   #     return
        print("Info written to", disk_info_short, "and", disk_info)       
        return 


def shutdown_and_reset( connection):     
    """ restarts serial connection to Arduino board (target) """
    connection.shutdown()
    print("Trigger board reset")
    connection.setup()
    return
    
#--------------------------------------------------------------------------------------------------------------
#
# List command options
#
# ------------------------------------------------------------------------------------------------------------- 
    
def list_commands():
    print("")
    print("-------------------- List of commands  ----------------------")
    print("")
    print("[t]: setup and test serial connection to board")
    print("[q]: quick scan. Reads tracks 0-4 and 17 to determine disk status")
    print("[d]: read disk VTOC and show table of contents (DOS 3.3)")
    print("[c]: capture disk in DOS3.3 format (.bin)")
    print("[a]: capture disk in raw format (.raw)")
    print("[r]: analyze .raw file and store result in .bin file")
    print("[g]: read .bin file and write table of contents to .info file")
    print("[R]: reset board (resetting serial connection)")
    print("[e]: exit")
    return
   
  
#--------------------------------------------------------------------------------------------------------------
#
# Main command loop
#
# ------------------------------------------------------------------------------------------------------------- 
print("")
print("------------------------------------------------------------------------------")
print("          treckr:       Apple II Disk Recovery Tool                           ")
print("                                                                              ")
print("          ", VERSION,sep='')
print("                                                                              ")
print("          Tool to read DOS 3.3 formatted 5.25 inch disks with 35/40 tracks    ")
print("          Please carefully study the README file                              ")
print("                                                                              ")
print(" NOTE:    -> BEFORE USAGE, ALWAYS CHECK THE DRIVE POWER SUPPLY AND THE      <-")
print("          -> WIRING FROM BOARD TO DRIVE. YOU NEED A DEDICATED POWER SUPPLY  <-")
print("          -> FOR THE DISK DRIVE TO PROVIDE +12V,-12V, +5V and GND.          <-")
print("          -> INCORRECT WIRING MAY DAMAGE DRIVE, DISKS, BOARD AND/OR HOST    <-")
print("          -> ALWAYS WRITE PROTECT DISKS BEFORE INSERTING THEM IN THE DRIVE. <-")
print("                                                                              ")
print("------------------------------------------------------------------------------")
print("")

connection = SerialConnection()

f_group1 = {"l": list_commands,
            "e": exit,
            "g": generate_catalog_from_bin_file,
            "r": analyze_raw_disk_from_bin_file}

f_group2 = {"t": test_serial,
            "q": quick_scan,
            "d": _read_disk_directory,
            "c": capture_dos_disk_to_host_file,
            "a": capture_raw_disk_to_host_file,
            "R": shutdown_and_reset }

while True:
    command = (input( "Choose a command ([l] list options): "))
 
    if command in f_group1:
        f_group1[command]()
    elif command in f_group2:
        f_group2[command]( connection)                	
    else:
        print("Unknown command")
 
