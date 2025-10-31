再创建一个web.txt,里面放入下载的网址


程序读取的是 “终端运行时所在的目录”，不是程序本身的存放目录。比如：
程序放在~/tools/image_to_cbz，但终端进入~/data并执行~/tools/image_to_cbz，程序会读取~/data/web.txt，生成的 CBZ 也在~/data。
系统兼容性：
若你的 Linux 是x86_64架构（主流笔记本 / 台式机），打包的程序可在其他x86_64的 Linux 发行版（Ubuntu、CentOS、Debian 等）运行；
若目标设备是 ARM 架构（如树莓派），需要在 ARM 架构的 Linux 上重新打包。
临时文件：运行时生成的temp_xxx临时文件夹，会在 CBZ 打包成功后自动删除；若中途出错，临时文件夹会保留，可手动删除。


参数名	作用说明	默认值	取值范围 / 示例
--web	指定网址文件（web.txt）的路径	./web.txt	例如：--web ~/docs/urls.txt
--workers	多线程下载的并发数（同时下载的图片数量）	10	正整数，例如：--workers 15
--retry	图片下载失败后的重试次数	3	正整数，例如：--retry 5
--quality	转换 JPG 图片的质量（数值越高画质越好，文件越大）	95	1-100，例如：--quality 80
--skip-existing	若目标 CBZ 文件已存在，直接跳过该网址的处理（避免重复下载和覆盖）	无（默认不跳过）	无需值，添加该参数即生效

基础用法（默认参数）
bash
./image_to_cbz
效果：读取当前目录的web.txt，用 10 个并发线程下载，重试 3 次，JPG 质量 95，不跳过已存在的 CBZ。
