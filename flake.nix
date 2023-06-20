{
  description = "A personal feed aggregator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/23.05";
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
  in {
    packages.${system} = let
      pkgs = (import nixpkgs {
        inherit system;
        overlays = [ self.overlays.default ];
      });
    in {
      default = self.packages.${system}.intake;
      inherit (pkgs) intake;
    };

    devShells.${system} = {
      default = let
        pkgs = nixpkgs.legacyPackages.${system};
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

    overlays.default = final: prev: {
      intake = final.python38Packages.buildPythonPackage {
        name = "intake";
        src = builtins.path { path = ./.; name = "intake"; };
        format = "pyproject";
        propagatedBuildInputs = with final.python38Packages; [ flask setuptools ];
      };
    };

    templates.source = {
      path = builtins.path { path = ./template; name = "source"; };
      description = "A basic intake source config";
    };

    nixosModules.default = {
      options = {};
      config.nixpkgs.overlays = [ self.overlays.default ];
    };

    nixosModules.intake = import ./module.nix;

    nixosConfigurations."demo" = makeOverridable nixosSystem {
      inherit system;
      modules = [
        nixos-shell.nixosModules.nixos-shell
        self.nixosModules.default
        self.nixosModules.intake
        ./demo
      ];
    };
  };
}
