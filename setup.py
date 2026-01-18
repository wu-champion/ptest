# setup.py
from setuptools import setup, find_packages

setup(
    name='ptest',
    version='1.0.0',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'ptest=ptest.cli:main',
            'p=ptest.cli:main',  # 简写命令
        ],
    },
    author='ptest team',
    author_email='ptest@example.com',
    description='A comprehensive testing framework',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/your-org/ptest',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    python_requires='>=3.7',
    install_requires=[
        # 此处无需额外依赖，因为使用标准库
    ],
)