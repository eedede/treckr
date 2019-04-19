# treckr
Retro tool to read Apple II formatted DOS 3.3 disk content using Arduino Mega2560 and store it on a host PC

------------------------------------------------------------------------------------------------------------------------------

  treckr: Retro tool to read Apple II DOS 3.3 formatted 5.25 inch disks using disk drive, Arduino board and host PC.
          Designed for (former) Apple II hobby enthusiasts who would like to recover private disk content.

  Version: 0.1  - March 2019 - Eckhard Delfs

------------------------------------------------------------------------------------------------------------------------------

## Which equipment is needed?
To be able to read DOS 3.3 disks and store them on a PC host via USB, the following equipment is needed:
- Apple DISK II drive (or compatible - during development Teac FD-55A was used) with 140/160KB storage capacity
- Arduino Mega2560 (or compatible) board with Atmel MPU ATmega2560; [treckr C](treckr/) files need to be installed here.
- Power supply to provide +12V, -12V, +5V and GND to disk drive; 12V power supply for Arduino board
- Host PC with Arduino IDE and python 3.5 installed

## How are the HW components connected to each other?
For connecting the 20-pin HW drive connector to the Arduino board, please have a look at the suggested [schematic](schematic/treckr_schematic.pdf) using a custom power supply. The overall HW tool kit used during development is shown [here](schematic/treckr_hw_pic).

Required wiring between Arduino and disk drive: 
- 4 wires for track motor control (driven by Arduino)
- 1 wire for disk motor enable/disable driven by Arduino)
- 1 wire for disk read/write control (driven by Arduino)
- 1 wire for disk read signal (driven by disk drive)
Note that Arduino Mega328 is **not** supported since treckr SW running on Arduino requires 8KB of onchip RAM 

The host PC is interfacing with Arduino via USB. PC needs to support Python 3.5. Only W10 has been tested, but other OS should work as well.

## Arduino PIN configuration
The Arduino board PIN configuration is as follows:

 - PIN 2:  drive read signal
 - PIN 22: drive write request (discriminate read/write)
 - PIN 24: drive on/off
 - PIN 34: enable/disable step motor phase 0
 - PIN 35: enable/disable step motor phase 1
 - PIN 36: enable/disable step motor phase 2
 - PIN 37: enable/disable step motor phase 3
  
 This PIN configuration can be changed in the Arduino SW if needed.
  
## Disk drive power supply  
The following choices are suggested:

- use original Apple II computer (or clone) power supply. 
   The required voltages can be obtained from one of the two pin headers of the disk interface card.
   Pay attention to the pin header pin-out. Check the signals with a multimeter.
- use/develop [custom power supply](schematic/treckr_schematic.pdf). The required voltages are: +12V, -12V and +5V. 
   
For prototyping, option b) was used. A standard power supply (18W) providing 15V DC output has been chosen. 
The +12V and +5V rails can be generated easily using 7812 and 7805 voltage regulators and additional capacitors for input/output. 
Note that decent heat sinks are needed, in particular for the 5V rail feeding the disk drive logic even when the motor is powered off.
The negative voltage (-12V) was realized using a charge pump DC->DC converter, such as IC7662A.
Two addditional 10uF capacitors are required for the charge pump.
The 12V rail needs to be connected to the Arduino board as well.

NOTE: Before enabling the power supply to the drive and connecting the drive control signals to the Arduino board, check the wiring.
      Info can be found in online Apple-2 material, also see below hints for literature.
      **Incorrect wiring may damage your Hardware!**
      Please note treckr is not designed to modify the disk content. However, it is strongly recommended to write protect disks before
      inserting them in the drive.

## Software Description
The general concept of treckr is shortly described as follows:
- The Arduino board interfaces with the drive. It sends commands to power on/off the drive, set read mode and move the track stepping motor.
- For reading the disk content, the drive read signal is connected to an Arduino external interrupt PIN.
- Each disk track contains ~50kbit of data. The Arduino SW configures the processor to collect 7KB of data, 
  which means that each read attempt allows to read slightly more than the content of one full track.
- The read signal does not come with a clock. Instead each read pulse indicates a logical "1". 
- The time between two read pulses allows to determine if the bit sequence to be decoded is "11", "101" or "1001". 
  For this reason the Arduino uses an 8-bit timer to measure the time interval between two read pulses. The bit decoding is done accordingly.
  The result is a similar processing as in the HW state machine handling of the Apple II disk controller.
  Dedicated assembly routines take care of read signal interrupt processing and data byte assembly.
  The Arduino SW does not analyze the track content, nor does it apply any bit filtering. 
  DOS 3.3 sector search and data field extraction are done on the host using the python sript.
  
- The PC host runs a python program [treckr.py](treckr.py) to control the Arduino. The tool is command based. 
  You need to update the global variable "SERIAL_PORT" to refer to the desired USB connection.
  Arduino and host use a 500k baud rate.
  The host ensures that the disk drive is only powered on during a read sequence.
  It stays e.g. disabled if only the serial connection to the Arduino board shall be tested.
  
- To scan the disks, the following approach is recommended:
   - use 'q' to quickly identify if the disk is readable and if it is DOS 3.3 formatted
   - use 'c' to read and store DOS 3.3 formatted disks 
   
   The content of the disk (35 or 40 tracks) is stored as a single file on the host file system.  The output is stored in binary (.bin)     files containing 35 or 40 tracks. Those may be processed by Apple II SW emulators.
   Each DOS 3.3 track consists of 16 sectors with 256 data bytes. The number of tracks is obtained from the VTOC info in track 17.
   Multiple disk read attempts will be tried if sectors cannot be decoded correctly.
   In case of read errors, the corrupt sectors are replaced by 256 zero bytes. Information on replaced sectors is stored in a dedicated file.
   - use 'd' to show the disk table of contents in original format on the screen. Nice feature :-)
   - use 'r' (raw) to store non-DOS 3.3 formatted disks. Note that in this case only one read attempt is done as the host 
     does not search for any byte pattern. You may use this function to investigate if a disk possibly contains non-DOS information. 
  
   - use 'g' to parse all .bin files on your host directory and generate a single file containing the table of contents for each of them.
  
  Enjoy reading your old disks and boot them in an emulator! There may be some very nice stuff to be digged out :-)
  
Note: treckr only supports reading DOS 3.3 disks. Writing is not supported.

## Related literature
The following books were considered very helpful:
- Jim Sathers, Understanding the Apple II, 1983, Quality SW, ISBN 0-912985-01-1 
  (online copy available  -> detailed info on disk drive connector pin-out can be found here)
- Bernd Ruhland, DOS 3.3 das Diskettenbetriebssystem des Apple-II, 1985, Franzis Verlag ISBN 3-7723-7691-6  
  (DOS 3.3 explained in low-level detail)
- Worth/Lechner, Beneath Apple DOS, 1982, Quality SW
  (online copy available)

  
The author reserves the right not to be responsible for the topicality, correctness, completeness or quality of the information provided. 
Liability claims regarding damage caused by the use of any information provided, including any kind of information 
which is incomplete or incorrect, will therefore be rejected. The tool is intended to be used for personal purposes only. 
