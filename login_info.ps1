Clear-Host
# Скрипт для получения логина и паролья из реестра Windows для отправки запросов в API игры
# найти подобный REG_BINARY в HKCU:\SOFTWARE\Pipeworks\GemsofWar\
$key = "76561198136873698LocalUsers_h2842827222"
# вписать имся своего пользователя из игры
$HeroName = "Tracy"

$bytes = Get-ItemPropertyValue -Path "HKCU:\SOFTWARE\Pipeworks\GemsofWar\" -Name $key
$text = [System.Text.Encoding]::UTF8.GetString($bytes)
# Удаляем нулевые символы
$cleanText = $text -replace "`0", ""
# Теперь парсим
$data = $cleanText | ConvertFrom-Json
$user = $data.UserList | Where-Object { $_.HeroName -eq $HeroName }
"Username: $($user.Username)"
"Password: $($user.Password)"
