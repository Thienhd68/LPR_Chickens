import pdfkit

# Cấu hình đường dẫn tuyệt đối tới wkhtmltopdf.exe
path_wkhtmltopdf = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

# Chuyển file HTML thành PDF
pdfkit.from_file("flow.html", "flowchart.pdf", configuration=config)

print("Đã xuất PDF thành công!")
