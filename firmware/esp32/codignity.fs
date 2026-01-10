decimal

\ Computational Dignity protocol (MVP)
\ TODO(thesis): Replace dummy sampling with real sensor read + timestamp source.

256 constant cd-fifo-size
create cd-fifo cd-fifo-size 2* cells allot  \ value, timestamp pairs

variable cd-head
variable cd-count
variable cd-tick

: cd-clear ( -- ) 0 cd-head ! 0 cd-count ! ;

: cd-min ( a b -- a|b ) 2dup < if drop else swap drop then ;
: cd-idx- ( idx n -- idx' ) swap cd-fifo-size + swap - cd-fifo-size mod ;

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

: cd-next-ts ( -- u ) cd-tick @ dup 1+ cd-tick ! ;
: cd-next-sample ( -- value ts ) cd-next-ts dup ;

: cd-parse-int-or ( default -- n )
  bl parse dup 0= if 2drop exit then
  rot drop evaluate ;

: cd-dump ( n -- )
  dup 0= if drop cd.!end exit then
  dup >r
  cd-head @ r@ cd-idx-
  r@ 0 ?do
    dup i + cd-fifo-size mod cd-read cd.!sample
  loop
  drop
  r> drop
  cd.!end ;

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

cd-clear
