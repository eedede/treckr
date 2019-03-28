/*--------------------------------------------------------------------------------------------------------------

  treckr - SW for Arduino ATmega 2560

  Version: 0.1

  Copyright (C) 2019 Eckhard Delfs

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.

  Apple II is a trademark of Apple Inc.

  Version history: 
  - 0.1: March 2019  - First version

 Note: SW Build gives memory warning (96% of dynamic memory used). Can be ignored
--------------------------------------------------------------------------------------------------------------*/

#include "defines.h"

/* ------------------------------
 *  Arduino HW Timer0 registers
 * ------------------------------*/
#define HW_TIM_CNT     TCNT0
#define HW_TIM_CTRLA   TCCR0A
#define HW_TIM_CTRLB   TCCR0B

/* ---------------------------------------------
 *  Arduino PIN definitions for HW drive control
 * ---------------------------------------------*/ 
// pins used for interrupt processing (cannot be arbitrary digital pin)
#define IN_PIN_FOR_DRIVE_READ_SIGNAL        (2)  /* input pin data read signal -> triggers INT4 interrupt during data capture */

// Output pin for write request; must be driven high, otherwise non-write protected disk will be overwritten!
#define OUT_PIN_FOR_WRITE_REQUEST           (22) /* output pin to configure read or write mode */

// Output PINs for step motor
#define OUT_PIN_FOR_TRACK_STEERING_PH0  (34)  /* enable/disable step motor phase 0 */
#define OUT_PIN_FOR_TRACK_STEERING_PH1  (35)  /* enable/disable step motor phase 1 */
#define OUT_PIN_FOR_TRACK_STEERING_PH2  (36)  /* enable/disable step motor phase 2 */
#define OUT_PIN_FOR_TRACK_STEERING_PH3  (37)  /* enable/disable step motor phase 3 */

#define OUT_PIN_FOR_DRIVE_ONOFF_CTRL    (24)  /* output pin to power drive on/off */

#define DRIVE_OFF (HIGH)
#define DRIVE_ON  (LOW)

#define PHASE_ON  (HIGH)
#define PHASE_OFF (LOW)
#define READ_MODE (HIGH)


/* -------------------------------------------
 *  Definitions for serial connection to host
 * ------------------------------------------*/
#define HOST_BAUD_RATE   (500000) // default baud rate, needs to be configured on host as well!

#define COMMAND_READ     (0x80)
#define COMMAND_TEST     (0xA0)
#define COMMAND_FINISH   (0xF0)

#define RESPONSE_OK      (0x40)
#define RESPONSE_FINISH  (0x60)
#define RESPONSE_ERROR   (0xEF)

/* -----------------------------------------------------
 *  Definition of data buffer size to capture read data
 * ----------------------------------------------------*/
 
#define SIZE_OF_DATA_BUFFER  (28) /* 28x256 bytes = 7KB, this is maximum value for ATmega 2560 */

/* ---------------------------------------------------------------------------------
 *  Definition data structures which are shared with assembly function
 *  
 *  round value: value 0..64 -> added to time stamp value 
 *  capture_data: buffer to store data read from drive
 *  size_capture_data: informs assembly function about size of capture_data buffer
 *  capture_timestamp: small buffer used by ISR to store time stamp value
 *  
 * ------------------------------------------------------------------------------*/
volatile byte round_value;        
volatile byte size_capture_data;                          
volatile byte capture_data[SIZE_OF_DATA_BUFFER*256];
volatile byte capture_timestamp[64] __attribute__((aligned(256))); // must be aligned as ISR triggers wrap around

// -----------------------------------------------------------------------------------------------------------------------
void _exit( void) {
  track_motor_all_phases_off();
  drive_off();
  exit(-1);
}

/* ----------------------------------------------------------------------------------------------------------------
 *  resetFunc()
 *  
 *  Resets Arduino -> jump to reset vector
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void(* resetFunc) (void) = 0; // not equivalent to HW reset


/* ----------------------------------------------------------------------------------------------------------------
 *  test_serial()
 *  
 *  Handler to test serial connection between target and host
 *  
 *  Waits for one-byte command
 *  COMMAND_TEST:   -> sends 1-byte response to host, followed by 7KB of formatted data 
 *  COMMAND_FINISH: -> sends 1-byte response to hist and returns to loop()
 *  any other       -> sends 1-byte error response to host
  *  ---------------------------------------------------------------------------------------------------------------
 */
void test_serial( void) {
  bool finished;
  word i;
  byte command;

  // mark initial track as "not read"
  finished=false;
  
  while( finished == false) {
    read_host_command(1, &command);
    switch(command) {
      case COMMAND_FINISH:
        finished = true;
        send_host_response(RESPONSE_FINISH);
        break;
      case COMMAND_TEST:
        send_host_response(RESPONSE_OK);
      
        // prepare data_bufer memory in onchip RAM
        for( i=0; i<7168; i++) {
          capture_data[i]=i&0xFF;
        }
        Serial.flush();
        Serial.write((byte*)capture_data, 7*1024); // send test data to host
        break; // wait for next command
      default:
        finished = true;
        send_host_response(RESPONSE_ERROR);
    }
  }
}

/* ----------------------------------------------------------------------------------------------------------------
 *  track_read()
 *  
 *  Handler to read one track from the disk
 *  
 *  Powers on drive when called, and powers it off when leaving
 *  
 *  Tracks are read only when requested by host. Host commands supported are
 *  a) COMMAND_READ with 2 parameters (track number, round value) -> response byte is returned (OK or INVALID_PARAMS) 
 *     Multiple COMMAND_READs can be issued by host 
 *  b) COMMAND_FINISH to return to main loop -> response byte is returned (OK) and main loop is entered
 *     Any other command is responded with RESPONSE_ERROR and main loop is re-entered
 * 
 *  ---------------------------------------------------------------------------------------------------------------
 */
void track_read( void) {
  bool finished;
  byte command[4];
  byte response;
  byte track_no;
  word i;

  drive_on(); // power on drive
  
  // mark initial track as "not read"
  finished=false;
  
  // start timer0 in 8bit resolution;
  HW_TIM_CTRLA=0;
  HW_TIM_CTRLB=0;
  HW_TIM_CTRLB |= (1<<CS10); // timer on

  // enable interrupt INT4
  EICRA = 0;
  EICRB = 3; // rising edge of INT4 generates interrupt

  while( finished == false) {
    track_no = 0xff;
    read_host_command(1, command);
    if( command[0] == COMMAND_FINISH) {
      finished = true;
      send_host_response( RESPONSE_FINISH);
    }
    else if(command[0] == COMMAND_READ) {
      // get READ command parameters
      read_host_command(2, command);
      track_no = command[0];    // track number to be read
      round_value = command[1]; // round value to be used by assembly function
      if (round_value == 0xFF) {
        // special case when requested to read with round value FF:
        // only issued when step motor shall be repositioned
        // for this purpose a short head bang is triggered to ensure track 0 is hit
        send_host_response(RESPONSE_OK);
        reset_hw_drive_state();    
      }
      else if((track_no > 39) || ( round_value >= 64)){
        send_host_response(0xFE); // invalid parameters
        finished=true;
      }
      else {
        // clear track memory (not really needed)
        for( i=0; i<7168; i++) {
          capture_data[i]=track_no;
        }
        // clear time stamp memory used by IRQ handler
        for( i=0; i<64; i++) {
          capture_timestamp[i]=0;
        }
        // position step motor to requested track
        if( set_track( track_no) == OK) { 
          send_host_response(RESPONSE_OK);
          Serial.flush();

          // capture 7KB of track data in onchip RAM
          noInterrupts();
          EIMSK = 0x10; // enable only INT4
          capture_track();
          EIMSK = 0x0; // disable external interrupts
          interrupts();
          
          // send track data to host
          Serial.write((byte*)capture_data, 7*1024);
        }
        else {
          finished = true;
          send_host_response(RESPONSE_ERROR);
        }
      }
    }
    else {
      finished = true;
      send_host_response(RESPONSE_ERROR);
    }
  }
  drive_off(); // power off drive
}

/* ----------------------------------------------------------------------------------------------------------------
 *  get_service_command()
 *  
 *  checks for next service request from host
 *  
 *  Waits forever if no data is present in serial input buffer
 *  Once data becomes availalble, fetches next command byte and returns
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
byte get_service_command( void) {

  bool command_found=false;
  byte command;

  while( !command_found) {
    if (Serial.available() > 0) {
      // read the incoming byte
     command = Serial.read();  
     command_found=true;
    }    
  }
  return command;  
}


/* ----------------------------------------------------------------------------------------------------------------
 *  read_host_command(byte, *byte)
 *  
 *  reads detailed command for given service
 *  
 *  number_of_bytes: number of bytes to be read
 *  data[]         : storage area for command bytes
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void read_host_command( byte number_of_bytes, byte *data) {  
  byte i;
  
  while (Serial.available() < number_of_bytes) {}

  for(i=0; i<number_of_bytes; i++) {
    data[i] = Serial.read();
  }
}

/* ----------------------------------------------------------------------------------------------------------------
 *  send_host_response(byte )
 *  
 *  writes one-byte response to host
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void send_host_response( byte response) {
   Serial.write( response);
}

/* ----------------------------------------------------------------------------------------------------------------
 *  setup()
 *  
 *  Called once by Arduino startup SW when board is reset, before entering loop()
 *  
 *  - configures serial connection to host
 *  - configure PIN modes to HW drive and configures default output values after board reset
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void setup() {
  
  Serial.begin(HOST_BAUD_RATE);                            // configure baud rate of serial connection to host
  
  pinMode( OUT_PIN_FOR_DRIVE_ONOFF_CTRL, OUTPUT);          // define output pin for drive power
  digitalWrite( OUT_PIN_FOR_DRIVE_ONOFF_CTRL, DRIVE_OFF);  // switch off drive
  
  pinMode( OUT_PIN_FOR_WRITE_REQUEST, OUTPUT);             // define output pin for read/write mode
  digitalWrite( OUT_PIN_FOR_WRITE_REQUEST, READ_MODE);     // configure read mode

  pinMode( IN_PIN_FOR_DRIVE_READ_SIGNAL, INPUT);           // configure input pin for read signal
  pinMode( OUT_PIN_FOR_TRACK_STEERING_PH0, OUTPUT);        // configure output pin for step motor phase 0
  pinMode( OUT_PIN_FOR_TRACK_STEERING_PH1, OUTPUT);        // configure output pin for step motor phase 1
  pinMode( OUT_PIN_FOR_TRACK_STEERING_PH2, OUTPUT);        // configure output pin for step motor phase 2
  pinMode( OUT_PIN_FOR_TRACK_STEERING_PH3, OUTPUT);        // configure output pin for step motor phase 3

  drive_off();                                             // switch off engine
  track_motor_all_phases_off();                            // switch off all step motor phases
  init_hw_drive_state();                                   // configure hw step motor position to undefined position
  size_capture_data = SIZE_OF_DATA_BUFFER;                 // configure default size of data buffer[] for storing read data from drive
  set_DELAY_slow();                                        // recommended setting for step motor delay
}

/* ----------------------------------------------------------------------------------------------------------------
 *  loop()
 *  
 *  Called by Arduino startup SW after having finished setup()
 *  
 *  - waits for 1-byte command from host
 *  - if command byte received, function calls corresponding handler. A response is only sent in the handler.
 *  - unknown command bytes are dropped without response
 *  - some options are for debug purposes only 
 *  ---------------------------------------------------------------------------------------------------------------
 */
void loop() {
  byte command;

  while( true) {

    command = get_service_command(); // read one-byte command to identify requested service

    switch( command) {
      case 'c':
      case 'C':
          reset_track_motor();
          break;
      case 'r':
      case 'R':
        track_read();
        break;
      case '0':
        resetFunc();  // trigger target reset
        break;
      case '+':
        increase_track();
        break;
      case '-':
        decrease_track();
        break;
      case '1':
        drive_on();
        break;
      case '2':
        drive_off();
        break;
      case 't':
      case 'T':
        test_serial();
        break;
      default: 
        break;
    }
  }
}
