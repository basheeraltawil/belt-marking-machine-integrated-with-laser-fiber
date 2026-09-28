from setuptools import find_packages, setup

package_name = 'belt_marking_ui'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Basheer Al-Tawil',
    maintainer_email='basheeraltaweel@gmail.com',
    description='Touchscreen operator UI (PyQt5 + rclpy) for the belt marking machine.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'operator_ui = belt_marking_ui.app:main',
        ],
    },
)
