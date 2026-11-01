# TCL 55P737 — чистый главный экран и четыре приложения

Настройка для Android TV 11, V8-R51MT05-LF1V620.021315: интерфейс
[CleanYourTV](https://github.com/Gathin23/cleanyourtv) с VK Видео, YouTube,
Happ и Кинопоиском. Системные компоненты сохраняются для работы телевизора.
Очистка использует обратимое отключение пакетов, без root и перепрошивки.
AirPlay для iPhone и Mac: [установка и проверка](windows/AIRPLAY-RU.md).

## Для Windows

[Инструкция, команды и восстановление](windows/README-RU.md).

Распакованный комплект содержит RUN.ps1, собранный APK и оригинальные инструменты
CleanYourTV. Нужны Google Platform-Tools и Python 3.10+. Java/Android Studio
на компьютере владельца для готовой сборки не нужны.

- Inspect: сохранить локальный снимок и прочитать сведения, без изменения Home.
- Launcher: записать исходное состояние, установить лаунчер штатным скриптом,
  применить профиль темой и проверить Home. Затем нужна проверка пультом владельца.
- Clean: после проверки нового Home отключить семь ненужных развлекательных
  приложений, сохраняя защиту системных пакетов оригинального disable.ps1.
- Restore: восстановить прежние состояния и Home из оригинальной записи.

На Home скрыты остальные пакеты из присланного списка. Отключение рекламных
и телеметрических служб TCL требует отдельного разбора отчёта
advertising-candidates.txt. Другие VPN остаются до проверки Happ.
Физическая установка, пульт и перезагрузка проверяются на телевизоре:
облачная среда не имеет прямого доступа к домашней сети владельца.

## Сборка

- [Профиль и список отключения](profiles/tcl-55p737/REVIEW.md).
- [Версия upstream и лицензия](vendor/cleanyourtv/UPSTREAM.md).
- tools/configure_launcher.py меняет только поддерживаемый config.xml.
- tools/package_windows_kit.py пакует APK, исходники, оригинальные инструменты,
  профиль и Windows-инструкцию. Кеши, личные данные и ключи подписи исключаются.

Upstream commit: 92fdd142566b8c55a5540a96fcdafb889141f644.
Для сборки нужны JDK 17, Android SDK platform 34 и build-tools 34.0.0.
Ниже /path/to/cleanyourtv — исходники этой ревизии в отдельном каталоге.

```sh
python3 tools/configure_launcher.py /path/to/cleanyourtv profiles/tcl-55p737/config.json --theme-overlay
```

Из /path/to/cleanyourtv/launcher, с настроенными JAVA_HOME и ANDROID_HOME:

```sh
./gradlew --no-daemon --max-workers=4 testReleaseUnitTest lintRelease assembleRelease
```

Проверьте подпись APK через apksigner verify --verbose --print-certs.
Из корня TCL_Roots создайте архив:

```sh
python3 tools/package_windows_kit.py /path/to/cleanyourtv
```

Готовый ZIP находится в dist/ (не отслеживается Git). Полный список скрытых
пакетов применяется через оригинальный theme.ps1, чтобы сохранить небольшой APK.
При смене ревизии сначала проверьте совместимость ресурсов и скриптов.

## Дополнительная утилита и тесты

tools/tcl_tv.py — отдельный помощник для чтения пакетов, открытия Google Play
и проверки/установки официального локального TV APK. Для очистки и нового
интерфейса используйте Windows-комплект.
Наблюдаемый пакет Happ — com.happproxy; происхождение установленного APK
этим не подтверждается. Сторонние APK Happ не скачиваются.

```sh
python3 -m unittest discover -s tests -v
git diff --check
```

Тесты Python проверяют профиль, неизменность посторонних ресурсов и сценарии
ADB-помощника с имитацией устройства. Работу реального ТВ они не подтверждают.
