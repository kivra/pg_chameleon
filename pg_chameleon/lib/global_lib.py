from pg_chameleon import mysql_engine, pg_engine
import yaml
import sys
import os
import time
import logging
import smtplib
class global_config(object):
	"""
		This class parses the configuration file which is in config/config.yaml and sets 
		the class variables used by the other libraries. 
		The constructor checks if the configuration file is present and if is missing emits an error message followed by
		the sys.exit() command. If the configuration file is successful parsed the class variables are set from the
		configuration values.
		The class sets the log output file from the parameter command.  If the log destination is stdout then the logfile is ignored
		
		:param command: the command specified on the pg_chameleon.py command line
	
	"""
	def __init__(self,config_name="default"):
		"""
			Class  constructor.
		"""
		self.config_dir = "config"
		config_file = '%s/%s.yaml' % (self.config_dir, config_name)
		self.config_name=config_name
		if not os.path.isfile(config_file):
			print("**FATAL - configuration file missing **\ncopy config/config-example.yaml to "+config_file+" and set your connection settings.")
			sys.exit()
		conffile = open(config_file, 'rb')
		confdic = yaml.load(conffile.read())
		conffile.close()
		try:
			self.source_name=confdic["source_name"]
			self.dest_schema=confdic["dest_schema"]
			self.mysql_conn=confdic["mysql_conn"]
			self.pg_conn=confdic["pg_conn"]
			self.my_database=confdic["my_database"]
			self.my_charset=confdic["my_charset"]
			self.pg_charset=confdic["pg_charset"]
			self.pg_database=confdic["pg_database"]
			self.my_server_id=confdic["my_server_id"]
			self.replica_batch_size=confdic["replica_batch_size"]
			self.tables_limit=confdic["tables_limit"]
			self.copy_mode=confdic["copy_mode"]
			self.hexify=confdic["hexify"]
			self.log_level=confdic["log_level"]
			self.log_dest=confdic["log_dest"]
			self.log_append=confdic["log_append"]
			
			self.sleep_loop=confdic["sleep_loop"]
			self.pause_on_reindex=confdic["pause_on_reindex"]
			self.sleep_on_reindex=confdic["sleep_on_reindex"]
			self.reindex_app_names=confdic["reindex_app_names"]
			
			
			self.log_file=confdic["log_dir"]+config_name+'.log'
			self.pid_file=confdic["pid_dir"]+"/pg_chameleon.pid"
			copy_max_memory=str(confdic["copy_max_memory"])[:-1]
			copy_scale=str(confdic["copy_max_memory"])[-1]
			try:
				int(copy_scale)
				copy_max_memory=confdic["copy_max_memory"]
			except:
				if copy_scale=='k':
					copy_max_memory=str(int(copy_max_memory)*1024)
				elif copy_scale=='M':
					copy_max_memory=str(int(copy_max_memory)*1024*1024)
				elif copy_scale=='G':
					copy_max_memory=str(int(copy_max_memory)*1024*1024*1024)
				else:
					print("**FATAL - invalid suffix in parameter copy_max_memory  (accepted values are (k)ilobytes, (M)egabytes, (G)igabytes.")
					sys.exit()
			self.copy_max_memory=copy_max_memory
		except KeyError as key_missing:
			print('Missing key %s in configuration file. check config/config-example.yaml for reference' % (key_missing, ))
			sys.exit()

	def get_source_name(self, config_name = 'default'):
		config_file = '%s/%s.yaml' % (self.config_dir, config_name)
		self.config_name=config_name
		if os.path.isfile(config_file):
			conffile = open(config_file, 'rb')
			confdic = yaml.load(conffile.read())
			conffile.close()
			try:
				source_name=confdic["source_name"]
			except:
				print('FATAL - missing parameter source name in config file %s' % config_file)
		return source_name
		
class replica_engine(object):
	"""
		This class acts as bridge between the mysql and postgresql engines. The constructor inits the global configuration
		class  and setup the mysql and postgresql engines as class objects. 
		The class setup the logging using the configuration parameter (e.g. log level debug on stdout).
		
		:param command: the command specified on the pg_chameleon.py command line
		
		
		
	"""
	def __init__(self, config, stdout=False):
		self.global_config=global_config(config)
		self.logger = logging.getLogger(__name__)
		self.logger.setLevel(logging.DEBUG)
		self.logger.propagate = False
		formatter = logging.Formatter("%(asctime)s: [%(levelname)s] - %(filename)s: %(message)s", "%b %e %H:%M:%S")
		
		if self.global_config.log_dest=='stdout' or stdout:
			fh=logging.StreamHandler(sys.stdout)
			
		elif self.global_config.log_dest=='file':
			if self.global_config.log_append:
				file_mode='a'
			else:
				file_mode='w'
			fh = logging.FileHandler(self.global_config.log_file, file_mode)
		
		if self.global_config.log_level=='debug':
			fh.setLevel(logging.DEBUG)
		elif self.global_config.log_level=='info':
			fh.setLevel(logging.INFO)
			
		fh.setFormatter(formatter)
		self.logger.addHandler(fh)

		self.my_eng=mysql_engine(self.global_config, self.logger)
		self.pg_eng=pg_engine(self.global_config, self.my_eng.my_tables, self.my_eng.table_file, self.logger)
		self.sleep_loop=self.global_config.sleep_loop
		
		self.pid_file=self.global_config.pid_file
	
	def init_replica(self):
		self.set_source_id('initialising')
		self.create_schema()
		self.copy_table_data()
		self.create_indices()
	
	def set_source_id(self, source_status):
		"""
			gets the source id for the current configuration
		"""
		self.pg_eng.set_source_id(source_status)
		
	
	def  create_schema(self):
		"""
			Creates the database schema on PostgreSQL using the metadata extracted from MySQL.
		"""
		self.pg_eng.create_schema()
		self.logger.info("Importing mysql schema")
		self.pg_eng.build_tab_ddl()
		self.pg_eng.create_tables()
	

	
	def  create_indices(self):
		"""
			Creates the indices on the PostgreSQL schema using the metadata extracted from MySQL.
			
		"""
		self.pg_eng.build_idx_ddl()
		self.pg_eng.create_indices()
	
	def create_service_schema(self):
		"""
			Creates the service schema sch_chameleon on the PostgreSQL database. The service schema is required for having the replica working correctly.
	
		"""
		self.pg_eng.create_service_schema()
		
	def upgrade_service_schema(self):
		"""
			Upgrade the service schema to the latest version.
			
		"""
		self.pg_eng.upgrade_service_schema()
		
	def drop_service_schema(self):
		"""
			Drops the service schema. The action discards any information relative to the replica.

		"""
		self.logger.info("Dropping the service schema")
		self.pg_eng.drop_service_schema()
	
	def check_running(self):
		""" checks if the process is running. saves the pid file if not """
		
		return_to_os=False 
		try:
			file_pid=open(self.pid_file,'r')
			pid=file_pid.read()
			file_pid.close()
			os.kill(int(pid),0)
			print("replica process already running with pid %s" % (pid, ))
			return_to_os=True
			if self.global_config.log_dest=='file':
				os.remove(self.global_config.log_file)
		except:
			pid=os.getpid()
			file_pid=open(self.pid_file,'w')
			file_pid.write(str(pid))
			file_pid.close()
			return_to_os=False
		return return_to_os
		
	def run_replica(self):
		"""
			Runs the replica loop. 
		"""
		if self.check_running():
			sys.exit()
		while True:
			self.my_eng.run_replica(self.pg_eng)
			self.logger.info("batch complete. sleeping %s second(s)" % (self.sleep_loop, ))
			time.sleep(self.sleep_loop)
	
	def list_config(self):
		list_config = (os.listdir(self.global_config.config_dir))
		print ("Available configurations")
		for file in list_config:
			lst_file = file.split('.')
			file_name = lst_file[0]
			file_ext = lst_file[1]
			if file_ext == 'yaml' and file_name!='config-example':
				source_name = self.global_config.get_source_name(file_name)
				source_status = self.pg_eng.get_source_status(source_name)
				print ("%s.yaml Source Name: %s - Status: %s" % (file_name, source_name, source_status ))
				
	def add_source(self):
		source_name=self.global_config.source_name
		dest_schema=self.global_config.dest_schema
		self.pg_eng.add_source(source_name, dest_schema)

	def drop_source(self):
		lst_yes= ['yes',  'Yes', 'y', 'Y']
		source_name = self.global_config.source_name
		drp_msg = 'Dropping the source %s will remove drop any replica reference.\n Are you sure? YES/No\n'  % source_name
		if sys.version_info[0] == 3:
			drop_src = input(drp_msg)
		else:
			drop_src = raw_input(drp_msg)
		if drop_src == 'YES':
			self.pg_eng.drop_source(self.global_config.source_name)
		elif drop_src in  lst_yes:
			print('Please type YES all uppercase to confirm')
		sys.exit()
	def copy_table_data(self):
		"""
			Copy the data for the replicated tables from mysql to postgres.
			
			After the copy the master's coordinates are saved in postgres.
		"""
		self.my_eng.copy_table_data(self.pg_eng, self.global_config.copy_max_memory)
		self.pg_eng.save_master_status(self.my_eng.master_status)


class email_lib(object):
	"""
		class to manage email alerts sent in specific events.
	"""
	def __init__(self, config, logger):
		self.config=config
		self.smtp_server=None
		self.logger=logger
	
	def connect_smtp(self):
		self.logger.info("establishing connection with to SMTP server")
		try:
			self.smtp_server = smtplib.SMTP(self.config["smtp_host"], self.config["smtp_port"])
			if self.config["smtp_tls"]:
				self.smtp_server.starttls()
			if self.config["smtp_login"]:
				self.smtp_server.login(self.config["smtp_username"], self.config["smtp_password"])
			
		except:
			self.logger.error("could not connect to the SMTP server")
			self.smtp_server=None
	
		
	def disconnect_smtp(self):
		if self.smtp_server:
			self.logger.info("disconnecting from SMTP server")
			self.smtp_server.quit()
	
	def send_restarted_replica(self):
		"""
			sends the email when restarting the replica process
		"""
		self.connect_smtp()
		self.disconnect_smtp()
	
