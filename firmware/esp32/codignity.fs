decimal

\ ESP32forth hides many useful implementation words in the `internals` vocabulary.
\ We opt-in so we can build a quiet, protocol-first command loop.
only forth definitions also internals

\ Computational Dignity protocol (ESP32 / ESP32forth)
\ TODO(thesis): Replace dummy sampling with real sensor read + timestamp source.
\ TODO(thesis): Persist history/source to flash (SPIFFS) and implement rollback.

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

: cd-parse-int-or ( default -- n )
  bl parse dup 0= if 2drop exit then
  rot drop evaluate ;

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
  ." ! Extended commands: explain source history define save" cr
  ." ! FIFO samples: " cd-fifo-size . cr
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

: save ( -- )
  \ Persist the current image to /spiffs/myforth (ESP32forth default).
  remember
  s" save" cd-hist-add
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

: cd-node ( -- )
  0 echo !
  0 arrow !
  cd-error-reset
  ['] cd-notfound 'notfound !
  begin
    ['] evaluate-buffer catch ?dup if
      0 state ! sp0 sp! fp0 fp! rp0 rp!
      cd-handle-exception
    then
    refill drop
  again ;

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
  ['] cd-node see-xt

  cd-old-type @ cd-type-xt!
  cd.!end ;

cd-clear
cd-hist-clear

only forth definitions
