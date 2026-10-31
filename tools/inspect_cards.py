with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('id="modal"')
print("id='modal' index:", idx)
if idx != -1:
    print(text[idx-50:idx+250])

idx_screen = text.find('id="login-screen"')
print("id='login-screen' index:", idx_screen)
if idx_screen != -1:
    print(text[idx_screen:idx_screen+400])

