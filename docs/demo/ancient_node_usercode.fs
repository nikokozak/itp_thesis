\ ----------------------------------------------------------
\ BEDROCK DEMO: "ANCIENT DEVICE" RECOVERY ROUTINES
\ ----------------------------------------------------------
\ Wiring (DOIT ESP32 DEVKIT V1):
\   - LAMP  on D23 / GPIO23 (LED + resistor)
\   - RADIO on D34 / GPIO34 (555 timer output, 0..3.3V)
\
\ NOTE: GPIO34 is input-only. Do not drive it.
\ ----------------------------------------------------------

: led.gpio    ( -- gpio ) 23 ;
: radio.gpio  ( -- gpio ) 34 ;

: led.on      ( -- ) led.gpio 1 digitalWrite ;
: led.off     ( -- ) led.gpio 0 digitalWrite ;
: led.init    ( -- )
  led.gpio OUTPUT pinMode
  led.off ;

: radio.init  ( -- )
  radio.gpio INPUT pinMode ;
: radio.read  ( -- bit ) radio.gpio digitalRead ;

\ Optional (REPL): mirror radio -> lamp for N ms.
: radio>led.step ( -- )
  led.gpio radio.read digitalWrite ;
: radio>led      ( n -- )
  0 do radio>led.step 1 ms loop ;
