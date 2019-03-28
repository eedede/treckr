// ----------------------------------------------------------------------------------------------------------------
// treckr drive control
// ----------------------------------------------------------------------------------------------------------------
 
#define MAX_LOGICAL_TRACK_NO               (39)  // logical track number range is 0..39
#define MAX_TRACK_REACHED                   (1)
#define TRACK_UNDEFINED                  (0xFF)
#define DELAY_AFTER_DRIVE_POWER_ON        (400)  // in ms, max value is 65535
#define DELAY_AFTER_DRIVE_POWER_OFF       (400)  // in ms, max value is 65535
#define DELAY_PHASE_CONTROL_ENA_AT_RESET   (55)  // phase enable delay [value*256us] during transition to track 0
#define DELAY_PHASE_CONTROL_OVL             (1)  // phase overlay delay [value*256us] 

static byte hw_track_no;        // current logical track position of step motor: 0..39 (if valid); TRACK_UNDEFINED if undefined
static bool hw_drive_enabled;   // current power state of motor (true: enabled)
static byte DELAY[MAX_LOGICAL_TRACK_NO+1];// delay time when switching between step motor

/* ----------------------------------------------------------------------------------------------------------------
 *  set_DELAY_default()
 *  
 *  configures fast mode delay for phase enable phases during track update
 *  ---------------------------------------------------------------------------------------------------------------
 */
void init_DELAY_default(void) {
  byte i;

  DELAY[0] = 55; // value*256 gives delay in us if target track is adjacent
  DELAY[1] = 44; // value*256 gives delay in us if target track has distance of 2
  DELAY[2] = 33; // value*256 gives delay in us if target track has distance of 3
  DELAY[3] = 22; // value*256 gives delay in us if target track has distance of 4
  DELAY[4] = 11; // value*256 gives delay in us if target track has distance of 5
  
  for(i=5; i<MAX_LOGICAL_TRACK_NO+1; i++) {
      DELAY[i] = 7;  // value*256 gives delay in us if target track has distance of >= 6
  }
 }
/* ----------------------------------------------------------------------------------------------------------------
 *  set_DELAY_slow()
 *  
 *  configures default delay for phase enable phases during track update (recommended)
 *  ---------------------------------------------------------------------------------------------------------------
 */
void set_DELAY_slow(void) {
 byte i;
 
  for(i=0; i<MAX_LOGICAL_TRACK_NO+1; i++) {
      DELAY[i] = 55;  // delay in us
  }
 }

/* ----------------------------------------------------------------------------------------------------------------
 *  hw_delay( word)
 *  
 *  Causes CPU to wait for [delay] us.
 *  Wait period 0..65535 us.
 *  ---------------------------------------------------------------------------------------------------------------
 */
void hw_delay_us( word delay) {
   while( delay > 10000) {
      delayMicroseconds( 10000);
      delay -= 10000;
   }
   delayMicroseconds(delay);
}

/* ----------------------------------------------------------------------------------------------------------------
 *  init_hw_drive_state()
 *  
 *  If enabled, switches off the drive and sets the track numer to invalid.
 *  
 *  Note: After calling, the variable hw_track_no indicates an invalid state. Hence, any call to a driver function
 *        which requires to change the track motor position first requires to reset the track
 *        motor to track 0.
 *  ---------------------------------------------------------------------------------------------------------------
 */
void reset_hw_drive_state( void) {
  byte i;
  
  hw_track_no += 2; // adjust real position by 2 
  if( hw_track_no > MAX_LOGICAL_TRACK_NO)
    hw_track_no = MAX_LOGICAL_TRACK_NO;

   for( i=hw_track_no+1; i>0; i--) {
      hw_decrease_track( i, DELAY_PHASE_CONTROL_ENA_AT_RESET, DELAY_PHASE_CONTROL_OVL);
    }
    track_motor_all_phases_off();
    hw_track_no=0;
    
}


/* ----------------------------------------------------------------------------------------------------------------
 *  init_hw_drive_state()
 *  
 *  If enabled, switches off the drive and sets the track numer to invalid.
 *  
 *  Note: After calling, the variable hw_track_no indicates an invalid state. Hence, any call to a driver function
 *        which requires to change the track motor position first requires to reset the track
 *        motor to track 0.
 *  ---------------------------------------------------------------------------------------------------------------
 */
void init_hw_drive_state( void) {
  hw_track_no = TRACK_UNDEFINED;
}

/* ----------------------------------------------------------------------------------------------------------------
 *  drive_on()
 *  
 *  Switches on HW drive by toggling the PIN for HW drive control.
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void drive_on( void) {
  int i;
  
  if( is_drive_enabled() == false) {
    digitalWrite( OUT_PIN_FOR_DRIVE_ONOFF_CTRL, DRIVE_ON);
    hw_drive_enabled = true;
    // delay 0.4s
    for( i=0; i<DELAY_AFTER_DRIVE_POWER_ON; i++) {
       hw_delay_us( 1000); // 1ms 
    }
  }
}

/* ----------------------------------------------------------------------------------------------------------------
 *  drive_off()
 *  
 *  Switches on HW drive by toggling the PIN for HW drive control.
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void drive_off( void) {
  int i;

  digitalWrite( OUT_PIN_FOR_DRIVE_ONOFF_CTRL, DRIVE_OFF);
  
  track_motor_all_phases_off();
  hw_drive_enabled = false;
  // delay 1s
  for( i=0; i<DELAY_AFTER_DRIVE_POWER_OFF; i++) {
     hw_delay_us( 1000); // 1ms 
  }
}

/* ----------------------------------------------------------------------------------------------------------------
 *  is_drive_enabled()
 *  
 *  Returns true if drive is powered on, false otherwise.
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
bool is_drive_enabled( void) {
  if( hw_drive_enabled == true) {
    return true;
  }
  return false;
}

/* ----------------------------------------------------------------------------------------------------------------
 *  track_motor_all_phases_off()
 *  
 *  Drives all 4 track motor signals to state "off".
 *  Note that after calling, hw_increase_track(), hw_decrease_track() one phase will remain enabled.
 *  This function ensures that all phases get shut down, once the track motor has been positioned.
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void track_motor_all_phases_off(void) {
  hw_delay_us( (word) DELAY_PHASE_CONTROL_OVL*256);
  digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH0, PHASE_OFF);  // 0V
  digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH1, PHASE_OFF);  // 0V
  digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH2, PHASE_OFF);  // 0V
  digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH3, PHASE_OFF);  // 0V
}

/* ----------------------------------------------------------------------------------------------------------------
 *  reset_track_motor()
 *  
 *  Powers on drive and sets the track motor to track "0".
 *  If HW track number is already defined (0..39), function will adjust the track motor accordingly
 *  otherwise the track motor is forced to track 0 by moving the arm in outer direction 80 times 
 *  (max number of physical tracks).
 *  
 *  Note: Keeps drive in state "on" at function exit.
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void reset_track_motor( void) {
  byte i;
  
  if( is_track_number_valid() == false)
  {
    drive_on();
    for( i=MAX_LOGICAL_TRACK_NO+1; i>0; i--) {
      hw_decrease_track( i, DELAY_PHASE_CONTROL_ENA_AT_RESET, DELAY_PHASE_CONTROL_OVL);
    }
    track_motor_all_phases_off();
    hw_track_no=0;
  }
  else {
    if( is_min_track_reached() == false) {
      drive_on();
      while( is_min_track_reached() == false) {
        decrease_track();
      }
      track_motor_all_phases_off();
    }
  }
}

/* ----------------------------------------------------------------------------------------------------------------
 *  is_track_number_valid()
 *  
 *  return true if hw_track_no is in range 0..39, false otherwise
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
bool is_track_number_valid( void) {
  if( hw_track_no <= MAX_LOGICAL_TRACK_NO) {
    return true;
  }
  return false;
}

/* ----------------------------------------------------------------------------------------------------------------
 *  is_min_track_reached()
 *  
 *  return true if hw_track_no is 0, false otherwise
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
bool is_min_track_reached( void) {
  if( hw_track_no == 0) {
    return true;
  }
  return false;
}

/* ----------------------------------------------------------------------------------------------------------------
 *  is_max_track_reached()
 *  
 *  return true if hw_track_no is MAX_LOGICAL_TRACK_NO, false otherwise
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
bool is_max_track_reached( void) {
  if( hw_track_no == MAX_LOGICAL_TRACK_NO) {
    return true;
  }
  return false;
}

/* ----------------------------------------------------------------------------------------------------------------
 *  set_track( byte)
 *  
 *  Sets track motor to desired position (0..MAX_LOGICAL_TRACK_NO)
 *  If driver is uninitialized, forces HW to go via track 0 first.
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
byte set_track( byte target_track) {
  byte i;
  byte current_track;

  // check if input parameter and drive state are OK
  if( (target_track > MAX_LOGICAL_TRACK_NO) || (false==is_drive_enabled())){
    return ERROR;
  }
  
  // check if HW settings are undefined
  if( is_track_number_valid() == false) {
    reset_track_motor();  // no, force track motor to goto track 0 first
  }
  current_track = hw_track_no;
  if( current_track == target_track) {
    return OK; // nothing to be done
  }
  else {
    if( current_track < target_track) {
      // current track number is smaller than target track number
      // move track motor to inner direction
      for( i= current_track; i < target_track; i++) {
        hw_increase_track( hw_track_no, DELAY[target_track-current_track], 5);
        hw_track_no++;
      }
    }
    else {
      // current track number is larger than target track number
      // move track motor to outer direction
      for( i= current_track; i > target_track; i--) {
        hw_decrease_track( hw_track_no, DELAY[current_track-target_track], 5);
        hw_track_no--;
      }
    }   
  }
  track_motor_all_phases_off(); // requires because one phase is still enabled
  return OK;
}


/* ----------------------------------------------------------------------------------------------------------------
 *  increase_track()
 *  
 *  Increase logical track by one
 *  Corresponds to advancing the step motor by two physical positions
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
byte increase_track( void) {
  // check if HW settings are undefined
  if( is_track_number_valid() == false) {
    return ERROR;
  }
  // check if max track is reached
  else if( is_max_track_reached()) {
    return ERROR;
  }
  if( is_drive_enabled()) {
    hw_increase_track( hw_track_no, 78, 5);
    hw_track_no++;
    track_motor_all_phases_off();
    return OK;
  }
  return ERROR;
}

/* ----------------------------------------------------------------------------------------------------------------
 *  decrease_track()
 *  
 *  Decrease logical track by one
 *  Corresponds to declining the step motor by two physical positions
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
byte decrease_track( void) {
  // check if HW settings are undefined
  if( is_track_number_valid() == false) {
    return ERROR;
  }
  // check if max track is reached
  if( is_min_track_reached()) {
    return ERROR;
  }
  if( is_drive_enabled()) {
    hw_decrease_track( hw_track_no, 78, 5);
    hw_track_no--;
    track_motor_all_phases_off();
    return OK;
  }
  return ERROR;
}


/* ----------------------------------------------------------------------------------------------------------------
 *  hw_increase_track(byte, byte, byte)
 *  
 *  Forces the step motor to adanvce by two steps in inner direction
 *  The phase programming depends on the current step motor position
 *  
 *  delay_handover [value*256us] : time to keep preceding phase enabled
 *  delay_on       [value*256us] : time to keep new phase enabled
 *  
 *  Current track number is even:
 *    1. Enable phase 1
 *    1a. Wait (delay on)
 *    2. Disable phase 0
 *    2a. Wait (delay off)
 *    3. Enable phase 2
 *    3a. Wait (delay on)
 *    4. Disable phase 1
 *    4a. Wait (delay off)
 *    
 *    Current track number is odd:
 *    1. Enable phase 3
 *    1a. Wait (delay on)
 *    2. Disable phase 2
 *    2a. Wait (delay off)
 *    3. Enable phase 0
 *    3a. Wait (delay on)
 *    4. Disable phase 3
 *    4a. Wait (delay off)
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void hw_increase_track( byte track_no, byte delay_on, byte delay_handover) {
   word i;
  
   if( false == ( track_no & 1)) // even track number?
   {
      // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH1, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);

       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH0, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);

      // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH2, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);
       
       // disable previous phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH1, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);
     }
       
     // odd track_number
     else  {

       // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH3, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);

       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH2, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);

      // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH0, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);
       
       // disable previous phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH3, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);
     }
}


/* ----------------------------------------------------------------------------------------------------------------
 *  hw_decrease_track(byte, byte, byte)
 *  
 *  Forces the step motor to adanvce by two steps in outer direction
 *  The phase programming depends on the current step motor position
 *  
 *  delay_handover [value*256us] : time to keep preceding phase enabled
 *  delay_on       [value*256us] : time to keep new phase enabled
 *  
 *  Current track number is even:
 *    1. Enable phase 3
 *    1a. Wait (delay on)
 *    2. Disable phase 0
 *    2a. Wait (delay off)
 *    3. Enable phase 2
 *    3a. Wait (delay on)
 *    4. Disable phase 3
 *    4a. Wait (delay off)
 *    
 *    Current track number is odd:
 *    1. Enable phase 1
 *    1a. Wait (delay on)
 *    2. Disable phase 2
 *    2a. Wait (delay off)
 *    3. Enable phase 0
 *    3a. Wait (delay on)
 *    4. Disable phase 1
 *    4a. Wait (delay off)
 *  
 *  ---------------------------------------------------------------------------------------------------------------
 */
void hw_decrease_track( byte track_no, byte delay_on, byte delay_handover) {
   byte i;
  
   if( false == ( track_no & 1)) // even track number?
   {
       // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH3, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);

       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH0, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);

      // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH2, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);
       
       // disable previous phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH3, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);
     }
     // odd track_number
     else  {
      
       // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH1, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);
      
       // disable previous phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH2, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);
     
       // enable next phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH0, PHASE_ON);  // 4-5V
       hw_delay_us( (word) delay_handover << 8);

       // disable previous phase
       digitalWrite( OUT_PIN_FOR_TRACK_STEERING_PH1, PHASE_OFF);  // 0V
       hw_delay_us( (word) delay_on << 8);
     }
}
