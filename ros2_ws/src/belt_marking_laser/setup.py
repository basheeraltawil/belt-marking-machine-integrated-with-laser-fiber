from setuptools import find_packages, setup

package_name = 'belt_marking_laser'

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
    description='LaserInterface abstraction, dry-contact pedal laser and simulated CO2 laser.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': []},
)
