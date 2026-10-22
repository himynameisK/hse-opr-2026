# задача 11 — открытые тесты
# формат: t 'ожидаемый вывод' 'аргументы…'; limit N — лимит в секундах
limit 10
t True 12.255.56.1
t True 1.2.3.4
t True 123.45.67.89
t False 1.2.3
t False 1.2.3.4.5
t False 123.456.78.90
t False 123.045.067.089
t False ''
t False abc.def.ghi.jkl
