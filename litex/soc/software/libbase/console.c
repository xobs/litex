#include <uart.h>
#include <console.h>
#include <stdio.h>
#include <stdarg.h>

FILE *stdin, *stdout, *stderr;

static console_write_hook write_hook;
static console_read_hook read_hook;
static console_read_nonblock_hook read_nonblock_hook;

void console_set_write_hook(console_write_hook h)
{
	write_hook = h;
}

void console_set_read_hook(console_read_hook r, console_read_nonblock_hook rn)
{
	read_hook = r;
	read_nonblock_hook = rn;
}

int putchar(int c)
{
	uart_write(c);
	if(write_hook != NULL)
		write_hook(c);
	return c;
}

char readchar(void)
{
	while(1) {
		if(uart_read_nonblock())
			return uart_read();
		if((read_nonblock_hook != NULL) && read_nonblock_hook())
			return read_hook();
	}
}

int readchar_nonblock(void)
{
	return (uart_read_nonblock()
		|| ((read_nonblock_hook != NULL) && read_nonblock_hook()));
}

int puts(const char *s)
{
	while(*s) {
		putchar(*s);
		s++;
	}
	putchar('\n');
	return 1;
}

void putsnonl(const char *s)
{
	while(*s) {
		putchar(*s);
		s++;
	}
}

void ui2a(unsigned int num, unsigned int base, int uc,char * bf)
{
  int n=0;
  unsigned int d=1;
  while (num/d >= base)
    d*=base;
  while (d!=0) {
    int dgt = num / d;
    num%= d;
    d/=base;
    if (n || dgt>0 || d==0) {
      *bf++ = dgt+(dgt<10 ? '0' : (uc ? 'A' : 'a')-10);
      ++n;
    }
  }
  *bf=0;
}
void i2a(int num, int base, char * bf)
{
  if (num<0) {
    num=-num;
    *bf++ = '-';
  }
  ui2a(num,base,0,bf);
}

#define PRINTF_BUFFER_SIZE 256

int vprintf(const char *fmt, va_list args)
{
	return 0;
	int len;
	char outbuf[PRINTF_BUFFER_SIZE];
	len = vscnprintf(outbuf, sizeof(outbuf), fmt, args);
	outbuf[len] = 0;
	putsnonl(outbuf);
	return len;
}

int printf(const char *fmt, ...)
{
	return 0;
	int len;
	va_list args;
	va_start(args, fmt);
	len = vprintf(fmt, args);
	va_end(args);
	return len;
}
