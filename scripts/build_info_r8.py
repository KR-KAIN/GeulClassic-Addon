"""Report actual interpreter and monotonic clock used by the Windows builder."""
import platform
import sys
import time


def main():
    clock=time.get_clock_info('monotonic')
    print('Build label: GeulClassic v0.4.54-R14-FIX1 BUILD COMPATIBILITY (R14 base)')
    print('Python:',sys.version.replace('\n',' '))
    print('Python executable:',sys.executable)
    print('Platform:',platform.platform())
    print('monotonic implementation:',clock.implementation)
    print('monotonic resolution:',clock.resolution)
    print('monotonic adjustable:',clock.adjustable)
    print('monotonic monotonic:',clock.monotonic)
    print('Screen resolution: recorded at runtime per capture profile; unknown at build time')
    print('DPI scale: recorded at runtime when game HWND is accessible; unknown at build time')
    print('Chat line height: measured at runtime per OCR segment; unknown at build time')
    print('Ink colour: measured at runtime per line; unknown at build time')


if __name__=='__main__':main()
