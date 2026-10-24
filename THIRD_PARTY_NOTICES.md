# Сторонние компоненты

Double Sound использует следующие библиотеки и программы. При распространении
готовой сборки соблюдайте условия их лицензий.

| Компонент | Назначение | Лицензия |
| --- | --- | --- |
| [PySide6 / Qt 6](https://www.qt.io/qt-for-python) | графический интерфейс, воспроизведение | LGPL-3.0 (используется динамическая компоновка) |
| [FFmpeg](https://ffmpeg.org/) (в составе Qt Multimedia) | декодирование аудио | LGPL-2.1-or-later |
| [mutagen](https://mutagen.readthedocs.io/) | чтение тегов и обложек | GPL-2.0-or-later |
| [NumPy](https://numpy.org/) | сравнение отпечатков | BSD-3-Clause |
| [Send2Trash](https://github.com/arsenetar/send2trash) | отправка файлов в корзину | BSD-3-Clause |
| [Chromaprint / fpcalc](https://acoustid.org/chromaprint) | аудиоотпечатки | LGPL-2.1-or-later |
| [PyInstaller](https://pyinstaller.org/) | сборка исполняемого файла | GPL-2.0-or-later с исключением для загрузчика |

`fpcalc.exe` для Windows распространяется в составе сборки. Исходный код
Chromaprint доступен на сайте проекта.

## Лицензия исходного кода и сборки

Исходный код Double Sound распространяется по лицензии MIT (см. `LICENSE`).
Готовая сборка включает компоненты под GPL/LGPL, поэтому при её передаче
третьим лицам необходимо соблюдать лицензии перечисленных выше компонентов.
Исходный код самого Double Sound доступен в этом репозитории.
