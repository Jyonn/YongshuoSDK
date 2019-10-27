from setuptools import setup, find_packages

setup(
    name='YongshuoX',
    version='0.0.1 alpha',
    keywords=('ys168', '永硕', 'YongShuo'),
    description='永硕网盘SDK',
    long_description='提供整套永硕网盘接口，包括资源读取、上传、编辑和删除',
    license='MIT Licence',
    url='https://github.com/lqj679ssn/YongshuoSDK',
    author='Adel Liu',
    author_email='i@6-79.cn',
    platforms='any',
    packages=find_packages(),
    install_requires=[
        'beautifulsoup4',
        'requests',
    ],
)
