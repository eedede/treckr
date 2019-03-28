/* ------------------------ */
/* treckr assembly routines */
/* ------------------------ */

extern volatile byte capture_timestamp[];    // 64 byte buffer to store 2-bit timestamps of incoming read signal interrupts
extern volatile byte capture_data[];         // 7 KB buffer to store MSB aligned 8-bit samples
extern volatile byte round_value;            // value to be added to timer0 cnt value before deciding on bit sequence: "1", "01", "001" or "0-01"
extern volatile byte size_capture_data;      // size of data buffer  (default is 28d, i.e. 0x1c)*256 -> 7168 = 7KB

/* 
 *  Interrupt service routine for INT4 interrupt
 *  
 *  Functionality:
 *  INT4 interrupt is raised any time a rising edge of INT4 is seen from the drive read signal
 *  The interrupt indicates that a logical "One" has been found
 *  In order to determine how many "Zeros" have passed since the previous logical "One", a timestamp based method is used.
 *  The interrupt service routine reads the value of the timer0 status (in us) and clears the timer afterwards.
 *  
 *  The interrupt service routine needs to cope with the requirement that a logical "One" may arrive every 64us.
 *  Using default interrupt service routines is not possible due to processing overhead caused by push/pop operations.
 *  For this reason the following approach is chosen:
 *  
 *  1) A naked Interrupt Service Routine (ISR) takes care of timer0 management and storage of the timestamp values in a circular buffer [capture_timestamp].
 *  2) A worker thread which runs in between the INT4 interrupts. If available, it fetches the next 2-bit timestamp value from the circular buffer
 *     and processes it. In case a complete data byte has been assembled, it is stored in the capture_data[] buffer.
 *     
 *     The ISR routine generates the 2-bit timestamp data as follows:
 *     x = (timer_value + round_value) >> 6. The meaning of the 4 code words is as follows:
 *     x: 00  ->  "0-01" read // invalid
 *     x: 01  ->     "1" read
 *     x: 10  ->    "01" read
 *     x: 11 - >   "001" read
 *     
 *     ISR and worker thread make collaborative use of CPU registers, so that register push/pops can be reduced to a minimum.
 *     
 *     ISR uses: r5, r16, r17(read), X
 */

ISR(INT4_vect, ISR_NAKED){             // uses 28 cycles 
  asm volatile(                        // 7,
    "in r5, __SREG__ \n"               // 1, save status register in r5
    "in r16, 0x26 \n"                  // 1, read timer0 to r16
    "out 0x26, r2 \n"                  // 1, clear timer0 
    "sbis 0x15, 0 \n"                  // 1-2, skip next instruction if TOV is set 
    "rjmp __no_tim_ofl \n"             // 2
    "sbi 0x15, 0 \n"                   // 2, clear TOV by setting bit 0 
    "ser r16 \n"                       // 1, r16=0xff
    
"__no_tim_ofl:\n"
    "add r16, r17 \n"                  // 1, r16+=r17, add round value without carry
    "rol r16 \n"                       // 1
    "rol r16 \n"                       // 1
    "rol r16 \n"                       // 1
    "andi r16, 3 \n"                   // 1
    "st X+, r16 \n"                    // 2, store 2-bit time stamp in array (capture_timestamp)
    "andi xl, 63 \n"                   // 1, trigger wrap around of sample buffer
"__exit:\n"
    "out  __SREG__, r5 \n"             // 1, restore status register from r5
    "reti  \n"                         // 5
  ::);
}

/* 
 *  Worker thread
 *  
 *  Interrupts must be disabled before calling this function!
 *  
 *  Processing
 *  
 *  The timestamp buffer read pointer is compared with timestamp buffer write pointer.
 *  If equal, worker thread is stopped.
 *  If not equal, worker thread picks next timestamp value and loads it into r21.
 *  Processing then depends on the value of r21: 00, 01, 02 or 03. 
 *  
 *  The new data byte (r18) is then either filled, completed or initialized.
 *  The following registers are used:
 *  r18 holds the current value of the next byte. 
 *  r21 holds the bit counter of the next byte.
 *  The bit counter is updated as follows:
 *  -> by 1, if new timestamp is "01" -> "1" is shifted in data byte r18
 *  -> by 2, if new timestamp is "10" -> "01" is shifted in data byte r18
 *  -> by 3, if new timestamp is "001" -> "001" is shifted in data byte r18
 *  -> If the bit counter reaches 8, the data byte is stored in data buffer[], and the loop counter is increased by one.
 *  ->   The surplus bits are fed into the next data byte. 
 *  ->   Note that the next data byte will always be initialized with a "1", i.e. leading zeros will be discarded.
 *  ->   The MSB of a valid data byte must be set.
 *  ->   Note: if a "00" timestamp is found, the current data byte is cleared and bit counter are initialized.
 *  ->   This is because only two consecutive zeros are allowed within a valid data word.
 *  
 *  Uses all  CPU registers
 */
void capture_track( void) {
    HW_TIM_CNT=0;
        asm volatile (
           "push r0\n"
           "push r1\n"
           "push r2\n"
           "push r3\n"
           "push r4\n"
           "push r5\n"
           "push r6\n"
           "push r7\n"
           "push r8\n"
           "push r9\n"
           "push r10\n"
           "push r11\n"
           "push r12\n"
           "push r13\n"
           "push r14\n"
           "push r15\n"
           "push r16\n"
           "push r17\n"
           "push r18\n"
           "push r19\n"
           "push r20\n"
           "push r21\n"
           "push r22\n"
           "push r23\n"
           "push r24\n"
           "push r25\n"
           "push r26\n"
           "push r27\n"
           "push r28\n"
           "push r29\n"
           "push r30\n"
           "push r31\n"

           "lds r23, size_capture_data\n"      // load size of data_buffer (in multiples of 256 bytes)
           "lds r17, round_value\n"            // init r17 with round value 
           "ldi yh, hi8(capture_timestamp)\n"  // init read pointer for timestamp buffer
           "ldi yl, lo8(capture_timestamp)\n"
           "ldi xh, hi8(capture_timestamp)\n"  // init write pointer for timestamp buffer
           "ldi xl, lo8(capture_timestamp)\n"
           "ldi zh, hi8(capture_data)\n"       // init Z write pointer for 7KB data buffer
           "ldi zl, lo8(capture_data)\n"
           "clr r25\n"                         // init loop counter(high), used to identify end of processing
           "clr r24\n"                         // init loop counter(low), used to identify end of processing
           "clr r2\n"                          // use r2 as zero register
           "clr r18\n"                         // r18 is used to assemble incoming bits before they are stored in capture_data
            
           "sei \n"                           // enable interrupts, now INT4 may fire

                                              // --------------------------
                                              // beginning of worker thread
                                              // --------------------------
"__chk_read_ptr:\n"
           "cp yl, xl\n"                      // 1, compare time stamp buffer read and write pointer
           "breq __chk_read_ptr\n"            // 1-2, // if equal, nothing to be done
           "ld r21, Y+\n"                     // 2, otherwise: fetch next 2-bit time stamp                       
           "cpi r18, 0\n"                     // 1, next_word=0?
           "breq __set_next_word_to_1\n"      // 1-2
     
           "cpi r21, 3\n"                     // 1
           "breq _001\n"                      // 1-2
           "cpi r21, 2\n"                     // 1
           "breq _01\n"                       // 1-2
           "cpi r21, 1\n"                     // 1
           "breq _1\n"                        // 1-2
      
"__set_next_word_to_1:\n" 
           "ldi r20,1\n"                      // 1, bit_counter=1
           "ldi r18,1\n"                      // 1, next_word=1
           "rjmp __inc_read_ptr\n"            // 2
          
"_1:\n"
           "lsl r18\n"                        // 1, next_word <<=1 
           "ori r18, 1\n"                     // 1, next_word |= 1
           "inc r20 \n"                       // 1, bit_counter +=1
           "cpi r20, 8\n"                     // 1, bit_counter=8?
           "brne __inc_read_ptr\n"            // 1-2
           "st Z+, r18 \n"                    // 2, store counter in array
           "clr r18\n"                        // 1, next_word=0
           "rjmp __chk_end\n"                 // 2
          
"_01:\n"
           "lsl r18\n"                        // 1, next_word <<=1  
           "inc r20 \n"                       // 1, bit_counter +=1
           "cpi r20, 8\n"                     // 1, bit_counter=8?
           "brne _01_2\n"                     // 1-2
           "st Z+, r18 \n"                    // 2, store counter in array
           "ldi r18, 1\n"                     // 1, next_word=1
           "ldi r20, 1\n"                     // 1, bit_counter=1
           "rjmp __chk_end\n"                 // 2    
          
"_01_2:\n"
           "lsl r18\n"                       // 1, next_word <<=1  
           "ori r18, 1\n"                     // 1, next_word |= 1
           "inc r20 \n"                       // 1, bit_counter +=1
           "cpi r20, 8\n"                     // 1, bit_counter=8?
           "brne __inc_read_ptr\n"            // 1-2
           "st Z+, r18 \n"                    // 2, store counter in array
           "clr r18\n"                        // 1, next_word=0
           "rjmp __chk_end\n"                 // 2
          
"_001:\n"
           "lsl r18\n"                        // 1, next_word <<=1  
           "inc r20 \n"                       // 1, bit_counter +=1
           "cpi r20, 8\n"                     // 1, bit_counter=8?
           "brne _001_2\n"                    // 1-2
           "st Z+, r18 \n"                    // 2, store counter in array
           "ldi r18, 1\n"                     // 1, next_word=1
           "ldi r20, 1\n"                     // 1, bit_counter=1
           "rjmp __chk_end\n"                 // 2    
          
"_001_2:\n"
           "lsl r18\n"                        // 1, next_word <<=1  
           "inc r20 \n"                       // 1, bit_counter +=1
           "cpi r20, 8\n"                     // 1, bit_counter=8?
           "brne _001_3\n"                    // 1-2
           "st Z+, r18 \n"                    // 2, store counter in array
           "ldi r18, 1\n"                     // 1, next_word=1
           "ldi r20, 1\n"                     // 1, bit_counter=1
           "rjmp __chk_end\n"                 // 2
          
"_001_3:\n"
           "lsl r18\n"                        // 1, next_word <<=1  
           "ori r18, 1\n"                     // 1, next_word |= 1
           "inc r20 \n"                       // 1, bit_counter +=1
           "cpi r20, 8\n"                     // 1, bit_counter=8?
           "brne __inc_read_ptr\n"            // 1-2
           "st Z+, r18 \n"                    // 2, store counter in array
           "clr r18\n"                        // 1, next_word=0
      
"__chk_end:\n"  
           "adiw r24, 1 \n"                   // 1, increment counter
           "cp  r25, r23 \n"                  // 1, compare with max size of data_buffer
           "breq __exit_capture \n"           // 1-2
"__inc_read_ptr:\n"
           "andi yl, 63 \n"                   // 1, update read pointer
           "rjmp __chk_read_ptr \n"           // 2
                                              // --------------------------
                                              // end of worker thread
                                              // --------------------------
"__exit_capture:\n"                   
           "cli \n"
           "pop r31\n"
           "pop r30\n"
           "pop r29\n"
           "pop r28\n"
           "pop r27\n"
           "pop r26\n"
           "pop r25\n"
           "pop r24\n"
           "pop r23\n"
           "pop r22\n"
           "pop r21\n"
           "pop r20\n"
           "pop r19\n"
           "pop r18\n"
           "pop r17\n"
           "pop r16\n"
           "pop r15\n"
           "pop r14\n"
           "pop r13\n"
           "pop r12\n"
           "pop r11\n"
           "pop r10\n"
           "pop r9\n"
           "pop r8\n"
           "pop r7\n"
           "pop r6\n"
           "pop r5\n"
           "pop r4\n"
           "pop r3\n"
           "pop r2\n"
           "pop r1\n"
           "pop r0\n"
         );
}
