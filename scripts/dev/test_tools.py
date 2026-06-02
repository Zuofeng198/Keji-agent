import sys, asyncio, os, tempfile, glob
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')


async def test():
    from nanobot.adapter import KejiAdapter
    adapter = KejiAdapter()
    tools = adapter.tools
    tmp = tempfile.gettempdir()

    ok = 0
    fail = 0

    async def t(name, args):
        nonlocal ok, fail
        tool = tools.get(name)
        if not tool:
            print('MISS', name)
            fail += 1
            return
        try:
            r = await tool.execute(**args)
            if '错误' in r[:100] or 'Error' in r[:100]:
                print('FAIL', name, ':', r[:80])
                fail += 1
            else:
                print('PASS', name)
                ok += 1
        except Exception as e:
            print('ERR ', name, ':', str(e)[:80])
            fail += 1

    # 基础
    await t('get_time', {})
    await t('calculator', {'expr': '1+2*3'})
    await t('knowledge_stats', {})
    await t('run_code', {'code': 'print("hello keji")'})

    # 文档 - 创建测试文件并验证
    test_doc = os.path.join(tmp, 'keji_test_doc.docx')
    await t('create_document', {'title': '测试', 'content': '测试内容', 'save_path': test_doc})
    if os.path.exists(test_doc):
        print('PASS create_document file exists')
        os.unlink(test_doc)
    else:
        print('FAIL create_document: file not created')

    # 文件夹
    test_dir = os.path.join(tmp, 'keji_test_dir')
    await t('create_folder', {'path': test_dir})
    if os.path.isdir(test_dir):
        print('PASS create_folder dir exists')
    else:
        print('FAIL create_folder: dir not created')

    await t('browse_files', {'path': tmp})
    await t('search_files', {'pattern': '*.py', 'folder': '.'})

    # 读文件
    tf = os.path.join(tmp, 'keji_readtest.txt')
    with open(tf, 'w', encoding='utf-8') as f:
        f.write('科吉测试内容')
    await t('read_document', {'path': tf})
    os.unlink(tf)

    # 数据分析
    await t('analyze_data', {'data_source': 'a,b\n1,2\n3,4'})
    await t('format_data', {'data': 'a,b\n3,4\n1,2', 'operation': 'sort', 'params': '0'})

    # 知识库
    await t('query_knowledge', {'query': 'test'})
    await t('index_knowledge', {'path': '.'})

    # 表格
    tbl = os.path.join(tmp, 'keji_test.xlsx')
    await t('create_table', {'headers': '姓名,年龄', 'rows': '张三,25|李四,30', 'save_path': tbl})
    if os.path.exists(tbl):
        print('PASS create_table file exists')
        os.unlink(tbl)
    else:
        print('FAIL create_table: file not created')

    # 压缩包
    tf2 = os.path.join(tmp, 'keji_arc.txt')
    with open(tf2, 'w') as f: f.write('test')
    zip_p = os.path.join(tmp, 'keji_test.zip')
    await t('create_archive', {'sources': tf2, 'output_path': zip_p})
    if os.path.exists(zip_p):
        print('PASS create_archive')
        await t('browse_archive', {'archive_path': zip_p})
        ext_dir = os.path.join(tmp, 'keji_extract')
        await t('extract_archive', {'archive_path': zip_p, 'output_dir': ext_dir})
        os.unlink(zip_p)
    else:
        print('FAIL create_archive: file not created')
    os.unlink(tf2)

    # 重命名
    old = os.path.join(tmp, 'keji_old.txt')
    new = os.path.join(tmp, 'keji_new.txt')
    with open(old, 'w') as f: f.write('test')
    await t('rename_files', {'directory': tmp, 'pattern': 's/keji_old/keji_new/'})
    if os.path.exists(new):
        print('PASS rename_files')
        os.unlink(new)
    else:
        print('FAIL rename_files')

    # 去重
    await t('deduplicate_files', {'directory': tmp})

    # 文件整理
    await t('organize_files', {'source_dir': tmp, 'mode': 'flat', 'preview': True})

    # 删除
    tf3 = os.path.join(tmp, 'keji_del.txt')
    with open(tf3, 'w') as f: f.write('test')
    await t('delete_file', {'path': tf3, 'confirm': True})

    print()
    print('PASS:', ok, 'FAIL:', fail)


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(test())
loop.close()
