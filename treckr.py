#--------------------------------------------------------------------------------------------------------------
#
#  treckr.py
#
#  Version: 0.1
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
#  - 0.1: March 2019  - First version
#
#--------------------------------------------------------------------------------------------------------------
import serial, time, binascii, os, errno, sys
#--------------------------------------------------------------------------------------------------------------
#
# Definition of USB serial port connected to board
#
# <<<<<<< CHANGE HERE FOR YOUR SETTINGS >>>>>>>>>>
#
SERIAL_PORT = "COM4"  
#
# ------------------------------------------------------------------------------------------------------------- 

serial_configured=False # default start condition of serial connection to board; not initialized
disk_dir_name="disks"   # name directory path containing the DOS 3.3 image disk files

#--------------------------------------------------------------------------------------------------------------
#
# Setup serial connection to board (target)
#
# Returns True if successfull
#
# ------------------------------------------------------------------------------------------------------------- 
def setup_serial():
  global serial_configured
  global target	
	
  try:
    if( serial_configured == False):
      string="Setting up serial port " + SERIAL_PORT + " ...."
      sys.stdout.write(string)
      target = serial.Serial(SERIAL_PORT, 500000, timeout=0.2)
      time.sleep(1) #give the connection a second to settle 	
      serial_configured=True     
      print("ok.") 
  except Exception as e:
    print("failed. Board connected? Wrong port?")
    print( str( e))
    return False
  return True

#--------------------------------------------------------------------------------------------------------------
#
# Reset serial connection to board (target)
#
# ------------------------------------------------------------------------------------------------------------- 
def reset_serial():
  global serial_configured
  if( serial_configured==True):
    target.close()
  serial_configured=False
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
#         accumulated_list: list of decoded sectors
#         track_dec:        16*256 bytes of decoded data fields 
#
# ------------------------------------------------------------------------------------------------------------- 
def track_read( target, track_no, repeat_counter):
	
  command = bytearray(3)	
  response = bytearray(1)

  attempts = 1
  accumulated_list=[]
  missing_physical_sector_list=[]
  missing_logical_sector_list=[]
  read_sectors=0
  track_dec=bytearray()   
  total_track_dec=[]  
  round_success_list=[]
  # round values to be used by assembly read function on board for each retry
  ROUNDS =[32, 32, 32, 32, 32, 32, 34, 34, 34, 36, 36, 36, 32, 32, 32, 30, 30, 36, 36]
  reset_counter=0 # counts track motor repositioning attempts
  finished=False
  rounds=len(ROUNDS) # default number of read attempts 
  if( repeat_counter==0):
    rounds=3 # fast mode for quick scan
	
  while( finished==False):
        # read requested track from drive
        track = read_disk_track_from_drive( target, track_no, ROUNDS[attempts-1])        
        # decode track and get content of physical sectors
        # note that the sector list may be incomplete
        read_track_no, sector_list, new_track_dec = track_decode( track.hex())
        if( track_no != read_track_no):
          attempts+=1 
        else:
          j=0
          k=0
          # search for new sectors in this read attempts
          # if available, add them to accumulated_list[] and store their data field in total_track_dec[]
          while j<16:
            if( j in sector_list):
              if( j not in accumulated_list):
               
                total_track_dec.append(new_track_dec[k])
                accumulated_list.append(j)                      
                read_sectors+=1
                print("Track: ", track_no,". Decoded Sectors:", read_sectors, end="\r", flush=True)
                round_success_list.append(ROUNDS[attempts-1])
              k+=1
            j+=1         
             
        # reposition track motor if all read attempts failed in current track position failed                   
        if(( attempts >= rounds) and (reset_counter < repeat_counter)):
          command[0] = 0x80 #READ
          command[1] = track_no
          command[2] = 255
          if( 3 == target.write(command)): 
            while target.in_waiting<1:
              continue
            response = target.read(1) 	 # don't check response
            reset_counter+=1
            attempts=1
                               
        # check if finished         
        if( read_sectors == 16) or (attempts >= rounds):
          finished=True
          j=0
          while j<16:
           if( j not in accumulated_list):
           	 # replace missing data sectors by all zero pattern
             accumulated_list.append(j)
             missing_physical_sector_list.append(j)
             total_track_dec.append([0 for i in range(256)])
           j+=1
        	# now reassemble 16 physical to 16 logical sectors
        	# e.g. logical sector 13 maps to physical sector 1
          physical_2_logical_sector_mapping_list=[0,13,11,9,7,5,3,1,14,12,10,8,6,4,2,15]
          for j in physical_2_logical_sector_mapping_list:
            track_dec +=bytes( total_track_dec[accumulated_list.index(j)])
          for j in missing_physical_sector_list:
            missing_logical_sector_list.append( physical_2_logical_sector_mapping_list.index(j))
        else:
        	attempts+=1
          	  

  if( read_sectors == 16):
    print("Track:", track_no, ". 16 sectors decoded correctly.       ")
  else:
    print("Track:",track_no, ". Incomplete track read. Sector(s) ", str( sorted( missing_logical_sector_list)), "could not be decoded.")

  return True, read_sectors, sorted( missing_logical_sector_list), round_success_list, track_dec
	

#--------------------------------------------------------------------------------------------------------------
#
# decode DOS 3.3 sector address field
#
# ------------------------------------------------------------------------------------------------------------- 
def check_address_field( header):
	# check if the header field trailer is at the expected position; check only the first two bytes (0xde, 0xaa)
  if header.find("deaa") != 22:
    return False, 0, 0 # trailer of sector address header corrupt
  volume_no = ((int(header[6:8],16)<<1)   | ((int(header[6:8],16)>>7)))   & int(header[8:10],16)
  track_no  = ((int(header[10:12],16)<<1) | ((int(header[10:12],16)>>7))) & int(header[12:14],16)
  sector_no = ((int(header[14:16],16)<<1) | ((int(header[14:16],16)>>7))) & int(header[16:18],16)
  sum_no    = ((int(header[18:20],16)<<1) | ((int(header[18:20],16)>>7))) & int(header[20:22],16)
  if( sum_no != (volume_no ^ track_no ^ sector_no)):
    return False, 0, 0 # error in sector address header checksum
  return True, track_no, sector_no # sector address header ok


#--------------------------------------------------------------------------------------------------------------
#
# decode DOS 3.3 sector data field
#
# ------------------------------------------------------------------------------------------------------------- 

# LUT = look up table for decoding 6-bit data words
LUT =                 [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                       0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x02, 0x03, 0x00, 0x04, 0x05, 0x06,
                       0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x08, 0x00, 0x00, 0x00, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
                       0x00, 0x00, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x00, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a,
                       0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1b, 0x00, 0x1c, 0x1d, 0x1e,
                       0x00, 0x00, 0x00, 0x1f, 0x00, 0x00, 0x20, 0x21, 0x00, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,                                 
                       0x00, 0x00, 0x00, 0x00, 0x00, 0x29, 0x2a, 0x2b, 0x00, 0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x32,
                       0x00, 0x00, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x00, 0x39, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f] 

"""
LUT =                 [0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d, 0x8e, 0x8f,
                       0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x00, 0x01, 0x98, 0x99, 0x02, 0x03, 0x9c, 0x04, 0x05, 0x06,
                       0xa0, 0xa1, 0xa2, 0xa3, 0xa4, 0xa5, 0x07, 0x08, 0xa8, 0xa9, 0xaa, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
                       0xb0, 0xb1, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0xb8, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a,
                       0xc0, 0xc1, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0x1b, 0xcc, 0x1c, 0x1d, 0x1e,
                       0xd0, 0xd1, 0xd2, 0x1f, 0xd4, 0xd5, 0x20, 0x21, 0xd8, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,                                 
                       0xe0, 0xe1, 0xe2, 0xe3, 0xe4, 0x29, 0x2a, 0x2b, 0xe8, 0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x32,
                       0xf0, 0xf1, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x00, 0x39, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f] 
"""

def check_data_field( datafield):
  
  data_256=[]
  # check if data field has correct trailer
  s = datafield.find("deaaeb")
  if( s!= 343*2):
    return False, data_256
  crc=0
  i=0

  # DOS 3.3 data fields consists of five parts
  # 3 byte header: d5-aa-ad
  # 256 bytes field containing encoded representation of lower 6-bits (torso) of the unencoded data field
  # 86 bytes field containing encoded representation of multiplexed higher 2-bits of unencoded data field;
  #          the unencoded 256 field is structured in 3 columns, where the 2-bit values of three columns are grouped in one code word
  #          the decoding of a 6bit->8bit value is done using a look up table (LUT)
  # 1 byte checksum
  # 3 byte trailer: 0xde-0xaa-0xeb
  
  # step 1 - decode first 86 bytes of encoded block in 6-bit values
  xor=0
  data_256_2_8=[]
  i=0
  while i<86:
    data_dec = xor ^ LUT[int(datafield[(i)*2:(i+1)*2],16) & 0x7f]
    data_256_2_8.insert(0, data_dec)
    xor = data_dec
    #print(hex(data_dec))
    i+=1  
  #print(data_256_2_8)
  
  # step 2 - decode remaining 256 bytes of encoded block in 6-bit values
  while i<342:
    data_dec = xor ^ LUT[int(datafield[(i)*2:(i+1)*2],16) & 0x7f]
    data_256.append(data_dec<<2)
    xor = data_dec
    #print(hex(data_dec))
    i+=1  

  # step 3 - verify checksum (XOR of data bytes)
  if (xor != LUT[int(datafield[342*2:343*2],16) & 0x7f]):
    i=0  
   # print("CRC error")
    return False, data_256
  else:
 #   print("CRC ok", crc)
    
   # print([hex(x) for x in data_256])
    #print([hex(x) for x in data_256_2_8])
    
    # step 4 - demux the 86 bytes containing 3 muxed pairs of 2 MSBs and insert them as MSBs next to the 6-bit torso fields of the remaining 256 byte field
    # processing is done in three columns: 84 bytes, 86 bytes, 86 bytes: first group is smaller because two 2-bit fields are unused (86*6=512+2*2)
    i=0
    while i<84: 
      p = ((data_256_2_8[2+i]>>4) & 3)
      if(p==2): p=1
      else: 
      	if(p==1): p=2
      data_256[255-i] |= p
      i+=1
      
    i=0  
    while i<86:
      p = ((data_256_2_8[i]>>2) & 3)
      if(p==2): p=1
      else: 
      	if(p==1): p=2
      data_256[171-i] |= p
      i+=1
      
    i=0  
    while i<86:
      p = ((data_256_2_8[i]) & 3)
      if(p==2): p=1
      else: 
        if(p==1): p=2
      data_256[85-i] |= p
      i+=1
   
  #print(bytearray(data_256))
#  print([hex(x) for x in data_256])
  return True, data_256


#--------------------------------------------------------------------------------------------------------------
#
# decode track into DOS 3.3 sector format
# 
# input:
#         track: data retrieved from board
# returns:
#         track_no: number of track
#         sector_list: list of successfully decoded sectors (sector header + data field)
#         track_dec: list of decoded data sectors (16*256 bytes). An invalid data field is replaced by an empty field (all 256 bytes set to 0)
#   
# ------------------------------------------------------------------------------------------------------------- 
def track_decode( track):
	
  track_dec=[]
  sector_list=[]
  sectors_found=0
  track_no=255 # undefined
  end=False
  
  while end == False:
    # search for 3 byte sector field header: 0xd5, 0xaa, 0x96
    s=track.find("d5aa96")
    if(s != -1):
      # sector field header has been found
      # check if remaining size of the track is smaller than a sector field (26 nibbles)
      if len(track) < 26:
        end=True
        break
      # check sector field header field content
      rc, track_no, sector_no = check_address_field(track[s:s+(2*13)])
      if( rc == True):
        # sector field is valid; advance by length of sector field header 
        track=track[s+(2*13):] 
        # now search for data field header
        t=track.find("d5aaad")
        if( t != -1):
        	# check if remaining length is sufficient to contain a complete data field
          if( len(track[t+6:]) < 349*2):
            end=True
            break
          # check that data field belongs to the current sector 
          if( t > 50*2):
            end=True
            break
          # decode data field ( d is data field)
          rc, d = check_data_field(track[t+6:t+(349*2)])
          if rc == True:
            # data field is ok; insert sector in result list
            if sector_no not in sector_list: 
              sector_list.insert(sector_no,sector_no)
              track_dec.insert(sector_no, d)
              sectors_found+=1
              if sectors_found == 16:
                end=True
                break
        else:
          # no data field found
          end=True
          break
      else:
      	# sector field is invalid
        #print("Header error")
        track=track[s+(2*13):]
    else:
    	#print("No (more) header sequence found")
    	end=True
 
  #print(sector_list)
 # print([hex(x) for x in track_dec[0]])
  return track_no, sector_list, track_dec
  

#--------------------------------------------------------------------------------------------------------------
#
# decode track 17 containing VTOC and list DOS3.3 directory (if table of contents is located in track 17)
#
# input:
#         sector_list:  list of sectors in this track
#         disk_dec:     16x256 bytes data field in this track
#         mode:         False: only print VTOC info
#                       True:  print VTOC and directory of files in DOS 3.3 format
# returns:
#         disk_no_tracks: number of tracks in this disk
#         disk_no_sectors: number of sectors in this disk
#         disk_os_version: DOS version of this disk 
# ------------------------------------------------------------------------------------------------------------- 
def analyze_track17( missing_sector_list, disk_dec, mode):
	
	# sector 0 contains VTOC info; check if present
  if(0 not in missing_sector_list):
  	# assemble VTOC info from sector 0
    disk_os_version=disk_dec[3]
    disk_volume=disk_dec[6]
    disk_no_tracks=disk_dec[0x34]
    disk_no_sectors=disk_dec[0x35]
    print("VTOC Info: Dos 3.", disk_os_version, ", Volume: ", disk_volume, ", Tracks: ", disk_no_tracks, ", Sectors: ", disk_no_sectors) 
 
    catalog_track =disk_dec[1]
    if( catalog_track==17):
      # read catalog    
      directory = read_catalog( disk_dec, 0)       
      for i in directory:
        print("{0} {1:03} {2}".format(i[1],i[2],i[0]))  
    else:
      print("Catalog Sector not in Track 17! Track is: ", catalog_track)  
  else:
    print("VTOC info not present.")
    disk_no_tracks=40
    disk_no_sectors=16
    disk_os_version=0
  return disk_no_tracks, disk_no_sectors, disk_os_version    
	

#--------------------------------------------------------------------------------------------------------------
#
# read catalog info and returns result in list
#
# input:
#         disk_dec   :  bytearray containing track17 or entire disk
#         tack_offset:  [0] means disk_dec only contains track17
#                       [!0] means disk_dec contains entire disk
# returns:
#         directory: list of directory entries
#                    file name (30 characters)
#                    file type ( 3 characters)
#                    file length
#                    track offset of first sector list sector
#                    sector offset of first sector list secto
#   
# ------------------------------------------------------------------------------------------------------------- 
def read_catalog( disk_dec, track_offset):
	
  directory = []
  catalog_track  = disk_dec[track_offset+1]
  catalog_sector = disk_dec[track_offset+2]
  
  if(( catalog_track > 39) or ( catalog_sector > 15)):
    print("Invalid catalog information. Track:", catalog_track, " Sector:", catalog_sector,".")
  else:    
    # print disk catalog
    file_type_table={0x00:"  T", 0x80:" *T", 0x01:"  I", 0x81:" *I", 0x02:"  A", 0x82:" *A", 0x04:"  B", 0x84:" *B", \
                     0x08:"  S", 0x88:" *S", 0x10:"  R", 0x90:" *R", 0x20:" AT", 0xA0:"*AT", 0x40:" BT", 0xC0:"*BT"}   
    finished=False
    while( False==finished):
    	# load next catalogue sector (cat)
      if( track_offset == 0): # only track17 is present in disk_dec
    	  offset = catalog_sector*256
      else: # all tracks are present in disk_dec
        offset = catalog_track*16*256 + catalog_sector*256
      cat=disk_dec[offset:offset+256]
      # look for next catalog sector and check validity of entries
      catalog_track = cat[1] # next catalog track
      catalog_sector= cat[2] # next catalog sector
      if(( catalog_track==0) or (catalog_track>39)):
        finished=True
      else:     	
        chk_value = cat[0] # first byte in catalogue sector should be 0
        i=3
        while (i < 11):
          chk_value |= cat[i]
          i+=1
        if( chk_value == 0):
        	# catalog sector seems valid; decode its content
          i=0
          offset=11 # descriptor offset
          # each catalog sector contains 7 file entries         
          while(i<7):
          	# determine file type
            if( (cat[offset] != 0) and (cat[offset] != 255)):
              file_type="UDF" #undefined file type as default             
              if( cat[offset+2] in file_type_table):
                file_type=file_type_table[cat[offset+2]]
              # determine file name
              file_name=cat[offset+3:offset+33]
              file_length=cat[offset+33]       
              j=0   
              # file name needs to be converted in ASCII    
              while(j<len(file_name)):                          
                file_name[j] = file_name[j] & 0x7f          
                j+=1        
            #  if( True==file_name.isascii()): // requires python 3.7
              directory.append([file_name.decode("ascii"), str(file_type), file_length, cat[offset], cat[offset+1]])
              offset+=35 # jump to next entry in sector
            i+=1
        else:
          finished=True 
        
  return directory
 
#--------------------------------------------------------------------------------------------------------------
#
# read sector usage list
#
# Using the table of contents, function assembles the track/sector lists for each file and stores them in a list.
#
# input:
#             disk_dec  :  bytearray containing entire disk
#             directory :  list containing disk table of contents
#     
# returns:
#      total_sector_list:  list of track/sector lists for each file in the directory
#                
# ------------------------------------------------------------------------------------------------------------- 	
def read_sector_list( disk_dec, directory):

  total_sector_list = []
  for i in directory:
    sector_list = []
    file_length = i[2] - 1  # sector list sector is subtracted from file length
    track_offset  = i[3]
    sector_offset = i[4]
    sector_list.append([track_offset, sector_offset]) # sector list is first entry
    if(( track_offset > 39) or (sector_offset > 15) or (file_length <= 0)): # check if entries are valid
      finished=True
    else:
      finished=False
    while( finished==False):
      offset = 16*256*track_offset+256*sector_offset
      _list  = disk_dec[offset:offset+256]
      if( len(_list) == 256):
        if(( _list[0] | _list[3] | _list[4]) == 0): # check if a few default entries are zero
          start = 12
          while(( file_length > 0) and (start <= 254)): # start=254 is last possible entry in sector
            sector_list.append([_list[start], _list[start+1]]) # add next track_sector entry
            file_length -= 1
            start +=2
            if( file_length == 0):
              finished=True
            if( start == 256):
              track_offset  = _list[1]
              sector_offset = _list[2]
              if( track_offset == 0): # last sector list sector belonging to this file?
                finished=True
        else:
          finished=True 
      else:
        sector_list.append(["INVALID", "INVALID"])  
        finished=True
    total_sector_list.append( sector_list)

  return total_sector_list
  
#--------------------------------------------------------------------------------------------------------------
#
# read disk track from drive
#
# ------------------------------------------------------------------------------------------------------------- 
def read_disk_track_from_drive( target, track_id, delay):  
  
  command = bytearray(3)	
  response = bytearray(1)
   
  command[0] = 0x80        # READ command
  command[1] = track_id    # track to be read
  command[2] = delay       #  delay used by target time stamp calculation
  if( 3 == target.write( command)):  
     while target.in_waiting<1:
       continue
     response = target.read(1) 	
     if( response[0] == 0x40):
       while target.in_waiting<7*1024:
         continue
       track_data = target.read(7*1024)
  return track_data
   
#--------------------------------------------------------------------------------------------------------------
#
# Test serial connection to board
#
# -------------------------------------------------------------------------------------------------------------
def test_serial():      
  print("Starting test of serial connection to target...")
  if( True == setup_serial()):
    # configure target for serial test mode
    target.write( bytearray("t", "utf-8"))  
  
    # send test serial command
    target.write( bytearray(b'\xa0'))     
  
    while target.in_waiting<1:
     continue
    response = target.read(1)  
    while target.in_waiting<7*1024:
      continue
    result = target.read(7*1024)
  
    # send test serial command
    target.write(bytearray(b'\xf0'))
    while target.in_waiting<1:
      continue
    response = target.read(1)  
    if( ord(response) == 0x60):
      print("Serial Test ok.")
    else:
      print("Serial Test not ok.  --> try again.")
      reset_serial()
  return  
  
#--------------------------------------------------------------------------------------------------------------
#
# Read DOS 3.3 directory from track 17
#
# Input: mode (True/False) 
#        False: read track 17, but do not show directory
#        True:  read track 17 and show directory
#
# ------------------------------------------------------------------------------------------------------------- 
def read_disk_directory( mode): 
  # configure target for single track read mode
  target.write( bytearray("r", "utf-8"))
          
  # read Track 17 containing VTOC and catalog sectors
  result, read_sectors, missing_sector_list, round_list, disk_dec = track_read( target, 17, 1)
  # configure target to leave single track read mode and enter main loop
  target.write( bytearray(b'.\xf0'))
  # wait for target response
  while target.in_waiting<1:
    continue
  response = target.read(1)       
             
  if( result == True):
    disk_no_tracks, disk_no_sectors, disk_version = analyze_track17( missing_sector_list, disk_dec, mode)   
    return True, disk_no_tracks, disk_no_sectors, disk_version
  else:
    return False, 0, 0, 0

 
#--------------------------------------------------------------------------------------------------------------
#
# Copy raw disk to host file
#
# ------------------------------------------------------------------------------------------------------------- 
def copy_raw_disk_to_host_file():
  if( True == setup_serial()):
    user_input = input( "Insert disk. Enter a filename for the disk (.raw is appended automatically): ")
    try:
      os.mkdir(disk_dir_name,0o700)
    except OSError as e:
      if(e.errno != errno.EEXIST):
        print("Cannot create directory",disk_dir_name,"in current directory")
        exit()
  
    disk_name = disk_dir_name + "/" + user_input+".raw"
    if(False==os.path.isfile(disk_name)):
      # configure target for single track read mode
      target.write(bytearray("r", "utf-8"))
      try:
        with open(disk_name,"wb") as file:
          i=0 
          while i<40:
          	# read track i with default delay (best effort mode, as track format is unknown)
            track_data = read_disk_track_from_drive( target, i, 32)
            print("Storing track:", i, "to file.")
            file.write( track_data)               
            i+=1 # move to next track              
          file.close()   
      except Exception as e:
        print("Error during generation of", disk_name,".")   
        print(str(e))
      #configure target for main command loop
      target.write(bytearray(b'.\xf0'))
      while target.in_waiting<1:
        continue
      response = target.read(1)       
    else:
      print("Error: File",disk_name,"already exists.")
  return
 

#--------------------------------------------------------------------------------------------------------------
#
# Runs quick scan of disk. Reads tracks 0-4, 17 and outputs DOS 3.3 sector analysis
#
# ------------------------------------------------------------------------------------------------------------- 
def quick_scan():
  if( True == setup_serial()):
    print("Runs quick scan of disk and outputs number of decoded DOS3.3 sectors in tracks 0-4, 17.")
    user_input = input( "Insert disk and press return: ")
     
    # configure board for single track read mode
    target.write( bytearray("r", "utf-8")) 
    
    i=0 
    while i<18:
      result, read_sectors, missing_sector_list, round_list, disk_dec = track_read( target, i, 0)
      i+=1 # move to next track
      if( i==5):
        i=17           
        
    # configure board to enter main command loop
    target.write( bytearray(b'.\xf0'))
    while target.in_waiting<1:
      continue
    response = target.read(1)  
  return
  
  
#--------------------------------------------------------------------------------------------------------------
#
# Copy DOS 3.3 disk to host file
#
# ------------------------------------------------------------------------------------------------------------- 
def copy_dos_disk_to_host_file():
  if( True == setup_serial()):
    rc, disk_no_tracks, disk_no_sectors, disk_os_version = read_disk_directory( False) # only read sector 0
    
    if( disk_os_version != 3):
      disk_no_tracks=35
      print("Invalid DOS version. Set number of tracks set to 35.")
  
    if( rc == True):
      user_input = input( "Insert disk. Enter a filename for the disk (.bin and .txt are appended automatically): ")
      try:
        os.mkdir( disk_dir_name,0o700)
      except OSError as e:
        if(e.errno != errno.EEXIST):
          print("Cannot create directory", disk_dir_name, "in current directory")
          exit()
    
      disk_name = disk_dir_name + "/" + user_input +".bin"
      disk_info = disk_dir_name + "/" + user_input +".txt"
      #print(disk_name)
      if(False==os.path.isfile( disk_name)):
      	
        # configure target for single track read mode
        target.write( bytearray("r", "utf-8"))
        try:
          with open( disk_name,"wb") as bin_file,\
               open( disk_info,"w")  as txt_file:
            i=0 
            while i<disk_no_tracks:
              info_text="Track: " + str(i) + ": "
              result, read_sectors, missing_sector_list, round_list, disk_dec = track_read( target, i, 2)
              if( read_sectors==16):
                info_text += "ok. "
              else:
                info_text += "corrupt sectors: " + str( missing_sector_list) +". "
              info_text += "List of round values: " + str( round_list) + ".\n"
              bin_file.write( disk_dec)               
              txt_file.write( info_text)
              i+=1 # move to next track              
            bin_file.close()  
            txt_file.close() 
        except Exception as e:
          print("Error during generation of", disk_name, "or", disk_info, ".")
          print( str(e))
          
        # configure target for main command loop
        target.write(bytearray(b'.\xf0'))
        while target.in_waiting<1:
          continue
        response = target.read(1)
      else:
        print("Error: File", disk_name, "or", disk_info, "already exists.")
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
  
  print("Directory", disk_dir_name, "will be parsed for disk image files (*.bin). Enter disk.")
  user_input = input("Enter output filename (file endings are added automatically): ")
  disk_info_short = disk_dir_name + "/" + user_input + ".info"
  disk_info       = disk_dir_name + "/" + user_input + "_with_sector_list.info"
  
  try:
    with open( disk_info, "w") as txt_file, \
         open( disk_info_short, "w") as txt_file_short:
      host_directory = os.listdir( disk_dir_name)
      
      for File in host_directory:
        if(File.rfind(".bin") != -1):
          print("Processing:", File)
          disk_directory = []
          File_path = disk_dir_name + "/" + File
          with open( File_path, "rb") as bin_file:
            disk_dec = bytearray( bin_file.read())
            
            # set track 17 as default track for directory search
            track_offset = 17*16*256
            if(( len(disk_dec) < track_offset) or (len(disk_dec) > 40*16*256)):
              message = "Error: File length <" + File + "> invalid (" + str(len(disk_dec)) + " bytes).\n"
              sys.stdout.write(message)
             # print("Error: Binary file <",disk_bin,"> too short.")
            else:
            	# generate disk table of contents
              disk_directory = read_catalog( disk_dec, track_offset)
              # generate list of sectors used by the files
              sector_list = read_sector_list (disk_dec, disk_directory)
        
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
    
  except Exception as e:
         print( "Error during generation of", disk_info, ".")
         print( str( e))
         return
  print("Info written to", disk_info_short, "and", disk_info)       
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
  print("[q]: quick scan. Reads tracks 0-4 and 17 to determine disk status")
  print("[d]: read disk VTOC and show table of contents (DOS 3.3)")
  print("[c]: copy DOS 3.3 disk to file")
  print("[a]: read raw disk to file")
  print("[g]: read .bin file and write table of contents to .info file")
  print("[t]: test serial connection to board")
  print("[R]: reset board (resetting serial connection")
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
print("          Version 0.1                                                         ")
print("                                                                              ")
print("          Tool to read DOS 3.3 formatted 5.25 inch disks with 35/40 tracks    ")
print("          Before usage, carefully study the README file                       ")
print("                                                                              ")
print(" WARNING: -> BEFORE USAGE, ALWAYS CHECK THE DRIVE POWER SUPPLY AND THE      <-")
print("          -> WIRING FROM BOARD TO DRIVE. YOU NEED A DEDICATED POWER SUPPLY  <-")
print("          -> FOR THE DISK DRIVE TO PROVIDE +12V,-12V, +5V and GND.          <-")
print("          -> INCORRECT WIRING MAY DAMAGE DRIVE, DISKS, BOARD AND/OR HOST    <-")
print("          -> ALWAYS WRITE PROTECT DISKS BEFORE INSERTING THEM IN THE DRIVE. <-")
print("                                                                              ")
print("          DISCLAIMER: USE AT YOUR OWN RISK.                                   ")
print("------------------------------------------------------------------------------")
print("")
while True:
  command = (input("Choose a command ([l] list options): "))
 
  if( command == "l"):
    list_commands()
      
  elif( command == "t"):
    test_serial()
         
  elif( command == "e"):
    exit()
    
  elif( command == "q"):
    quick_scan()
    
  elif( command == "d"):
    setup_serial()
    read_disk_directory( True) # read all sectors of Track 17 and list directory
           
  elif( command == "R"):
    reset_serial()
    print("Trigger board reset")
    setup_serial()       
            
  elif( command == "c"):
  	copy_dos_disk_to_host_file()
  	
  elif( command == "a"):
  	copy_raw_disk_to_host_file()
  	
  elif( command == "g"):
  	generate_catalog_from_bin_file()
  	
  else:
    print("Unknown command")
   
      
