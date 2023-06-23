{ pkgs, ... }:

{
  system.stateVersion = "22.11";

  # Set up two users to demonstrate the user separation
  users.users.alice = {
    isNormalUser = true;
    password = "alpha";
    uid = 1000;
    packages = [ pkgs.intake ];
  };

  users.users.bob = {
    isNormalUser = true;
    password = "beta";
    uid  = 1001;
    packages = [ pkgs.intake ];
  };

  # Set up intake for both users with an entry point at port 8080
  services.intake = {
    listen.port = 8080;
    users.alice.enable = true;
    users.bob.enable = true;
  };

  # Expose the vm's intake revproxy at host port 5234
  virtualisation.forwardPorts = [{
    from = "host";
    host.port = 5234;
    guest.port = 8080;
  }];

  # Mount the demo content for both users
  nixos-shell.mounts = {
    mountHome = false;
    mountNixProfile = false;
    cache = "none";

    extraMounts = {
      "/mnt/alice" = ./alice;
      "/mnt/bob" = ./bob;
      "/mnt/sources" = ./sources;
    };
  };

  # Create an activation script that copies and chowns the demo content
  # chmod 777 because the users may not exist when the activation script runs
  system.activationScripts = 
  let
    userSetup = name: uid: ''
      ${pkgs.coreutils}/bin/mkdir -p /home/${name}/.local/share/intake
      ${pkgs.coreutils}/bin/cp -r /mnt/${name}/* /home/${name}/.local/share/intake/
      ${pkgs.coreutils}/bin/chown -R ${uid} /home/${name}
      ${pkgs.findutils}/bin/find /home/${name} -type d -exec ${pkgs.coreutils}/bin/chmod 755 {} \;
      ${pkgs.findutils}/bin/find /home/${name} -type f -exec ${pkgs.coreutils}/bin/chmod 644 {} \;
    '';
  in
  {
    aliceSetup = userSetup "alice" "1000";
    bobSetup = userSetup "bob" "1001";
  };

  # Put the demo sources on the global PATH
  environment.variables.PATH = "/mnt/sources";

  # Include some demo instructions
  environment.etc.issue.text = ''
    ###
    # Welcome to the intake demo! Log in as `alice` with password `alpha` to begin.
    #
    # Exit the VM with ctrl+a x, or switch to the qemu console with ctrl+a c and `quit`.
    ###
  '';
  users.motd = ''
    ###
    # To set a password for the web interface, run `intake passwd` and set a password.
    #
    # Within this demo VM, the main intake entry point can be found at localhost:8080. This is also exposed on the host machine at localhost:5234. After you set a password, navigate to localhost:5234 on your host machine and log in to see the web interface.
    #
    # Try updating the `echo` source by running `intake update -s echo`. You should see a new item after refreshing the source's feed. This source uses `env` source configuration, so use `intake edit -s echo` or the web interface to change the message, then update the source again.
    #
    # Updating a source will also trigger intake to update the user crontab. If you run `crontab -l`, you should see that the `currenttime` source has a crontab entry. You can change this source's cron schedule in the source config.
    ###
  '';
}
