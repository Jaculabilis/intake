{
  description = "A personal feed aggregator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/22.11";
    # Included to support default.nix and shell.nix
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
    # Included to support the integration test in tests/demo.nix
    nixos-shell.url = "github:Mic92/nixos-shell";
    nixos-shell.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, flake-compat, nixos-shell }:
  let
    inherit (nixpkgs.lib) makeOverridable nixosSystem;
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
  in {
    packages.${system} = {
      default = self.packages.${system}.intake;
      intake = pkgs.python38Packages.buildPythonPackage {
        name = "intake";
        src = builtins.path { path = ./.; name = "intake"; };
        format = "pyproject";
        propagatedBuildInputs = with pkgs.python38Packages; [ flask setuptools ];
      };
    };

    devShells.${system} = {
      default = let
        pythonEnv = pkgs.python38.withPackages (pypkgs: with pypkgs; [ flask black pytest ]);
      in pkgs.mkShell {
        packages = [
          pythonEnv
          pkgs.nixos-shell
          # We only take this dependency for htpasswd, which is a little unfortunate
          pkgs.apacheHttpd
        ];
        shellHook = ''
          PS1="(develop) $PS1"
        '';
      };
    };

    templates.source = {
      path = builtins.path { path = ./template; name = "source"; };
      description = "A basic intake source config";
    };

    nixosModules.intake = import ./module.nix self;

    nixosConfigurations."demo" = makeOverridable nixosSystem {
      inherit system;
      modules = [
        nixos-shell.nixosModules.nixos-shell
        self.nixosModules.intake
        (import ./demo self)
      ];
    };
  };
}
