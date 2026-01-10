decimal

\ ESP32forth hides many useful implementation words in the `internals` vocabulary.
\ We opt-in so we can build a quiet, protocol-first command loop.
only forth definitions also internals also interrupts

\ Computational Dignity protocol (ESP32 / ESP32forth)
\ TODO(thesis): Replace dummy sampling with real sensor read + timestamp source.
\ TODO(thesis): Persist history/source to flash (SPIFFS) and implement rollback.
\ TODO(thesis): Replace `bye`-based reboot with a clean ESP32 restart primitive.

256 constant cd-fifo-size
create cd-fifo cd-fifo-size 2* cells allot  \ value, timestamp pairs

variable cd-head
variable cd-count
variable cd-tick

: cd-clear ( -- ) 0 cd-head ! 0 cd-count ! ;

: cd-min ( a b -- a|b ) 2dup < if drop else swap drop then ;
: cd-submod ( idx n mod -- idx' ) >r swap r@ + swap - r> mod ;
: cd-adv ( a n -- a' n' ) 1- swap 1+ swap ;
: cd-drop1 ( a n -- a' n' ) 1- swap 1+ swap ;
: cd-space? ( c -- f ) dup bl = swap 9 = or ;
: cd-skip-spaces ( a n -- a' n' )
  begin dup while over c@ cd-space? if cd-adv else exit then repeat ;

: cd-addr ( idx -- addr ) 2* cells cd-fifo + ;

: cd-write ( value ts idx -- )
  cd-addr dup cell+ >r
  over r@ !            \ ts -> addr+cell
  swap drop !          \ value -> addr
  r> drop ;

: cd-inc-count ( -- )
  cd-count @ cd-fifo-size < if cd-count @ 1+ cd-count ! then ;

: cd-push ( value ts -- )
  cd-head @ cd-write
  cd-head @ 1+ cd-fifo-size mod cd-head !
  cd-inc-count ;

: cd-read ( idx -- value ts ) cd-addr dup @ swap cell+ @ ;

: cd.!end ( -- ) ." ! end" cr ;
: cd.!ok ( -- ) ." ! ok" cr ;
: cd.!sample ( value ts -- ) ." ! " . . cr ;
: cd.# ( a n -- ) ." # " type cr ;

variable cd-error-emitted
: cd-error-reset ( -- ) 0 cd-error-emitted ! ;
: cd-error-on ( -- ) -1 cd-error-emitted ! ;
: cd.#err ( a n -- ) cd-error-on ." # err " type cr ;
: cd.#code ( n -- ) cd-error-on ." # code " . cr ;
: cd-consume-line ( -- ) #tib @ >in ! ;
: cd-rest-of-line ( -- a n )
  tib >in @ +  #tib @ >in @ - ;

: cd-next-ts ( -- u ) cd-tick @ dup 1+ cd-tick ! ;
: cd-next-sample ( -- value ts ) cd-next-ts dup ;

: 2swap ( a b c d -- c d a b ) rot >r rot r> swap ;

: cd-parse-int-or ( default -- n )
  bl parse dup 0= if 2drop exit then
  rot drop evaluate ;

\ ------------------------------------------------------------
\ Files (SPIFFS) helpers

4 constant cd-safe-gpio  \ DOIT ESP32 DEVKIT V1: user wired button between GPIO4 and GND.

64 constant cd-path-max
create cd-myforth-path cd-path-max allot
variable cd-myforth-n

: cd-myforth-build ( -- )
  remember-filename dup cd-myforth-n ! cd-myforth-path swap cmove
  cd-myforth-path cd-myforth-n @ + 0 swap c! ;

: cd-myforth$ ( -- a n ) cd-myforth-path cd-myforth-n @ ;

64 constant cd-lkg-max
create cd-lkg-path cd-lkg-max allot
variable cd-lkg-n

: cd-lkg-build ( -- )
  cd-myforth$ dup cd-lkg-n ! cd-lkg-path swap cmove
  s" .lkg" cd-adv dup >r
  cd-lkg-path cd-lkg-n @ + swap cmove
  cd-lkg-n @ r@ + dup cd-lkg-n !
  cd-lkg-path + 0 swap c!
  r> drop ;

: cd-lkg$ ( -- a n ) cd-lkg-path cd-lkg-n @ ;

: cd-file-exists? ( a n -- f )
  r/o open-file dup 0<> if
    drop drop 0 exit
  then
  drop close-file drop -1 ;

\ ------------------------------------------------------------
: cd-dump ( n -- )
  dup 0= if drop cd.!end exit then
  dup >r
  cd-head @ r@ cd-fifo-size cd-submod
  r@ 0 ?do
    dup i + cd-fifo-size mod cd-read cd.!sample
  loop
  drop
  r> drop
  cd.!end ;

\ ------------------------------------------------------------
\ History (in-memory ring; persistence TODO)

32 constant cd-hist-max
120 constant cd-hist-maxlen
cd-hist-maxlen 1+ constant cd-hist-entry

create cd-hist cd-hist-max cd-hist-entry * allot
variable cd-hist-head
variable cd-hist-count

: cd-hist-clear ( -- ) 0 cd-hist-head ! 0 cd-hist-count ! ;
: cd-hist-addr ( idx -- a ) cd-hist-entry * cd-hist + ;
: cd-hist-write ( a n idx -- )
  cd-hist-addr >r
  cd-hist-maxlen cd-min
  dup r@ c!
  r@ 1+ swap cmove
  r> drop ;
: cd-hist-inc-count ( -- )
  cd-hist-count @ cd-hist-max < if cd-hist-count @ 1+ cd-hist-count ! then ;
: cd-hist-add ( a n -- )
  2dup cd-hist-head @ cd-hist-write
  cd-hist-head @ 1+ cd-hist-max mod cd-hist-head !
  cd-hist-inc-count
  2drop ;
: cd-hist-oldest ( -- idx )
  cd-hist-head @ cd-hist-count @ cd-hist-max cd-submod ;
: cd-hist-read ( idx -- a n )
  cd-hist-addr dup c@ swap 1+ swap ;

\ Protocol commands (match PROTOCOL_REFERENCE.md)

: ? ( -- )
  ." ! id smart" cr
  ." ! mcu esp32" cr
  ." ! ver codignity-0.1" cr
  ." ! fifo " cd-fifo-size . cr
  ." ! children 0" cr
  cd.!end ;

: s ( -- )
  cd-next-sample 2dup cd-push cd.!sample
  cd.!end ;

: n ( -- )
  ." ! " cd-count @ . cr
  cd.!end ;

: d ( -- )
  cd-count @ cd-parse-int-or
  cd-count @ cd-min
  cd-dump ;

: c ( -- )
  cd-clear
  cd.!ok
  cd.!end ;

: explain ( -- )
  ." ! I am a smart node running ESP32forth on an ESP32." cr
  ." ! I speak a human-readable, line-oriented protocol over UART." cr
  ." ! Core commands: ? s n d c" cr
  ." ! Extended commands: explain source history define save validate safe-save restart recover rollback repl" cr
  ." ! FIFO samples: " cd-fifo-size . cr
  cd.!end ;

: cd-validate? ( -- f )
  depth dup 0= swap -1 = or
  fdepth 0= and ;

: validate ( -- )
  cd-validate? if
    cd.!ok
  else
    ." ! fail stack" cr
  then
  cd.!end ;

: history ( -- )
  cd-hist-count @ 0 ?do
    cd-hist-oldest i + cd-hist-max mod cd-hist-read
    ." ! " type cr
  loop
  cd.!end ;

: define ( -- )
  cd-rest-of-line cd-skip-spaces
  2dup cd-hist-add
  cd-consume-line
  evaluate
  cd.!ok
  cd.!end ;

\ ------------------------------------------------------------
\ Protocol-mode loop + error handling

: cd-route ( a n -- )
  \ TODO(thesis): Implement routing to child nodes over UART/RS-485.
  s" route_unimplemented" cd.#err
  ." # target " type cr
  cd.!end ;

: cd-notfound ( a n f -- )
  0= if 2drop exit then
  2dup over c@ [char] @ = if
    cd-drop1 cd-route
    cd-consume-line
    2drop
    exit
  then
  s" notfound" cd.#err
  2dup cd.#
  cd.!end
  cd-consume-line
  2drop ;

: cd-handle-exception ( n -- )
  cd-error-emitted @ if drop cd-error-reset exit then
  s" exception" cd.#err
  cd.#code
  cd.!end
  cd-error-reset ;

variable cd-exit
variable cd-old-echo
variable cd-old-arrow
variable cd-old-notfound

: repl ( -- )
  -1 cd-exit !
  cd.!ok
  cd.!end ;

: cd-node ( -- )
  echo @ cd-old-echo !
  arrow @ cd-old-arrow !
  'notfound @ cd-old-notfound !

  0 cd-exit !
  0 echo !
  0 arrow !
  cd-error-reset
  ['] cd-notfound 'notfound !
  begin
    ['] evaluate-buffer catch ?dup if
      0 state ! sp0 sp! fp0 fp! rp0 rp!
      cd-handle-exception
    then
    cd-exit @ 0= if
      refill drop
      0
    else
      -1
    then
  until
  cd-old-notfound @ 'notfound !
  cd-old-echo @ echo !
  cd-old-arrow @ arrow ! ;

: cd-safe-setup ( -- )
  cd-safe-gpio INPUT pinMode
  cd-safe-gpio gpio_pullup_en drop ;

: cd-safe-pressed? ( -- f ) cd-safe-gpio digitalRead 0= ;

: cd-boot ( -- )
  cd-safe-setup
  cd-safe-pressed? if
    ." SAFE: pressed; staying in REPL" cr
  else
    cd-node
  then ;

: cd-ensure-autostart ( -- ) ['] cd-boot 'cold ! ;

: save ( -- )
  \ Persist the current image to /spiffs/myforth and keep protocol auto-start enabled.
  cd-ensure-autostart
  remember
  s" save" cd-hist-add
  cd.!ok
  cd.!end ;

: safe-save ( -- )
  cd-validate? if
    cd-ensure-autostart
    cd-lkg$ save-name
    remember
    s" safe-save" cd-hist-add
    cd.!ok
  else
    ." ! fail validate" cr
  then
  cd.!end ;

: restart ( -- )
  ." ! rebooting" cr
  cd.!end
  100 ms
  bye ;

: recover ( -- )
  \ Factory reset: delete saved images and reboot.
  cd-myforth$ delete-file drop
  cd-lkg$ delete-file drop
  cd.!ok
  cd.!end
  100 ms
  bye ;

: rollback ( -- )
  \ Minimal rollback: restore last-known-good image (myforth.lkg).
  1 cd-parse-int-or dup 1 <> if
    drop s" unsupported" cd.#err cd.!end exit
  then
  drop
  cd-lkg$ cd-file-exists? 0= if
    s" rollback_missing" cd.#err cd.!end exit
  then
  cd.!ok
  cd.!end
  cd-lkg$ restore-name ;

\ Source: decompile key words, prefixing each output line with "! ".
variable cd-old-type
variable cd-line-start
create cd-ch 1 allot

: cd-type-xt@ ( -- xt ) ['] type >body @ ;
: cd-type-xt! ( xt -- ) ['] type >body ! ;
: cd-raw-type ( a n -- ) cd-old-type @ execute ;
: cd-raw-emit ( c -- ) cd-ch c! cd-ch 1 cd-raw-type ;
: cd-prefix ( -- ) s" ! " cd-raw-type ;
: cd-type-prefixed ( a n -- )
  begin dup while
    over c@ dup 13 = over 10 = or if
      cd-raw-emit -1 cd-line-start !
    else
      cd-line-start @ if cd-prefix 0 cd-line-start ! then
      cd-raw-emit
    then
    cd-adv
  repeat 2drop ;

: source ( -- )
  cd-type-xt@ cd-old-type !
  ['] cd-type-prefixed cd-type-xt!
  -1 cd-line-start !

  ['] ? see-xt
  ['] s see-xt
  ['] n see-xt
  ['] d see-xt
  ['] c see-xt
  ['] explain see-xt
  ['] history see-xt
  ['] define see-xt
  ['] save see-xt
  ['] validate see-xt
  ['] safe-save see-xt
  ['] restart see-xt
  ['] recover see-xt
  ['] rollback see-xt
  ['] repl see-xt
  ['] cd-boot see-xt
  ['] cd-node see-xt

  cd-old-type @ cd-type-xt!
  cd.!end ;

cd-clear
cd-hist-clear
cd-myforth-build
cd-lkg-build
sp0 sp!
fp0 fp!

only forth definitions
